from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, and_, select
from sqlalchemy.orm import Session, joinedload

from app.models.account import Account, AccountSubtype
from app.models.category import Category
from app.models.entry import Entry
from app.models.import_staging import ImportStaging, StagingStatus
from app.models.plaid import PlaidAccount
from app.models.holding import Holding
from app.models.account_mark import AccountMark
from app.models.transaction import Transaction
from app.schemas.register import (
    CategorySuggestion,
    HoldingSummary,
    RegisterRow,
    RegisterResponse,
)
from app.services.categorization import (
    matching_rules,
    resolve_category_id,
)
from app.services.category_assignment import apply_category_to_transaction
from app.services.holdings import list_holdings, portfolio_value
from app.services.payee_normalization import infer_direction
from app.services.register_labels import (
    activity_label_from_recognition,
    register_column_labels,
)
from app.services.ledger import account_balance
from app.services.transaction_recognition import RecognizedTransaction, conflict_group_key, recognize_transaction


def _charge_payment(amount: Decimal, subtype: AccountSubtype) -> tuple[Decimal | None, Decimal | None]:
    if amount < 0:
        return abs(amount), None
    if amount > 0:
        return None, amount
    return None, None


def _category_for_row(db: Session, txn: Transaction, account_id: int) -> tuple[int | None, str | None]:
    for entry in txn.entries:
        if entry.category_id and entry.account_id != account_id:
            cat = db.get(Category, entry.category_id)
            return entry.category_id, cat.name if cat else None
    for entry in txn.entries:
        if entry.category_id:
            cat = db.get(Category, entry.category_id)
            return entry.category_id, cat.name if cat else None
    return None, None


OPENING_PREFIX = "opening:"
BASELINE_PREFIX = "baseline:"


def _is_investment_subtype(subtype: AccountSubtype) -> bool:
    return subtype.value in ("brokerage", "retirement", "hsa")


@dataclass
class _PendingRegisterRow:
    entry: Entry
    txn: Transaction
    txn_date: date
    payee: str
    memo: str | None
    charge: Decimal | None
    payment: Decimal | None
    running_balance: Decimal
    category_id: int | None
    category_name: str | None
    recognized: RecognizedTransaction
    activity_label: str | None
    cash_direction: str | None
    is_cleared: bool
    is_transfer: bool
    investment_type: str | None
    investment_subtype: str | None
    security_name: str | None
    quantity: Decimal | None
    price: Decimal | None


def _row_conflict_key(row: _PendingRegisterRow) -> str:
    return conflict_group_key(
        row.recognized,
        payee=row.payee or "",
        memo=row.memo,
    )


def _uncategorized_id(db: Session) -> int | None:
    cat = db.query(Category).filter(Category.slug == "uncategorized").first()
    return cat.id if cat else None


def _category_name(db: Session, category_id: int) -> str | None:
    cat = db.get(Category, category_id)
    return cat.name if cat else None


def _suggestions_for_categories(
    db: Session, category_ids: set[int], rules: list
) -> list[CategorySuggestion]:
    suggestions: list[CategorySuggestion] = []
    seen: set[int] = set()
    for rule in rules:
        if rule.category_id in seen:
            continue
        cat = db.get(Category, rule.category_id)
        if not cat:
            continue
        seen.add(rule.category_id)
        suggestions.append(
            CategorySuggestion(
                category_id=rule.category_id,
                category_name=cat.name,
                rule_id=rule.id,
                label=rule.pattern,
            )
        )
    for category_id in sorted(category_ids - seen):
        cat = db.get(Category, category_id)
        if not cat:
            continue
        suggestions.append(
            CategorySuggestion(
                category_id=category_id,
                category_name=cat.name,
                rule_id=None,
                label=None,
            )
        )
    return suggestions


def _apply_and_finalize(
    db: Session,
    pending: _PendingRegisterRow,
    category_id: int,
    pattern_categories: dict[str, set[int]],
) -> None:
    apply_category_to_transaction(db, pending.entry, category_id)
    pending.category_id = category_id
    pending.category_name = _category_name(db, category_id)
    pattern_categories[_row_conflict_key(pending)].add(category_id)


def _resolve_categories(
    db: Session,
    pending_rows: list[_PendingRegisterRow],
    *,
    account_subtype: str,
) -> bool:
    """Auto-assign unambiguous categories; return True if any rows were updated."""
    pattern_categories: dict[str, set[int]] = defaultdict(set)
    for row in pending_rows:
        if row.category_id:
            pattern_categories[_row_conflict_key(row)].add(row.category_id)

    uncategorized_id = _uncategorized_id(db)
    changed = False

    for row in pending_rows:
        if row.category_id is not None:
            continue
        if row.recognized.is_internal_transfer:
            continue

        group_key = _row_conflict_key(row)
        direction = infer_direction(
            row.payee,
            row.memo,
            charge=row.charge,
            payment=row.payment,
        )
        matched_rules = matching_rules(
            db,
            payee=row.payee,
            memo=row.memo or "",
            direction=direction,
            account_subtype=account_subtype,
        )
        rule_category_ids = {rule.category_id for rule in matched_rules}
        peer_category_ids = pattern_categories.get(group_key, set())
        ambiguous_ids = rule_category_ids | peer_category_ids

        if len(ambiguous_ids) > 1:
            continue

        if len(rule_category_ids) == 1:
            _apply_and_finalize(db, row, next(iter(rule_category_ids)), pattern_categories)
            changed = True
            continue

        if len(peer_category_ids) == 1:
            _apply_and_finalize(db, row, next(iter(peer_category_ids)), pattern_categories)
            changed = True
            continue

        resolved = resolve_category_id(
            db,
            payee=row.payee,
            memo=row.memo,
            investment_subtype=row.investment_subtype,
            investment_type=row.investment_type,
            security_name=row.security_name,
            amount=Decimal(str(row.entry.amount)),
            account_subtype=account_subtype,
            is_transfer=row.is_transfer,
        )
        if resolved and resolved != uncategorized_id:
            _apply_and_finalize(db, row, resolved, pattern_categories)
            changed = True

    if changed:
        db.commit()
    return changed


def _finalize_row_metadata(
    db: Session,
    pending: _PendingRegisterRow,
    pattern_categories: dict[str, set[int]],
    *,
    account_subtype: str,
) -> tuple[list[CategorySuggestion], bool, str | None]:
    group_key = _row_conflict_key(pending)
    assigned_cats = pattern_categories.get(group_key, set())
    conflict = len(assigned_cats) > 1

    remember_pattern: str | None = None
    suggestions: list[CategorySuggestion] = []

    if pending.category_id is None:
        remember_pattern = pending.recognized.canonical_key
        direction = infer_direction(
            pending.payee,
            pending.memo,
            charge=pending.charge,
            payment=pending.payment,
        )
        matched_rules = matching_rules(
            db,
            payee=pending.payee,
            memo=pending.memo or "",
            direction=direction,
            account_subtype=account_subtype,
        )
        rule_category_ids = {rule.category_id for rule in matched_rules}
        ambiguous_ids = rule_category_ids | assigned_cats

        if len(ambiguous_ids) > 1:
            suggestions = _suggestions_for_categories(db, ambiguous_ids, matched_rules)
        elif len(ambiguous_ids) == 1:
            # Single match but row still uncategorized (e.g. internal transfer skipped)
            pass

    return suggestions, conflict, remember_pattern


def get_register(
    db: Session,
    account_id: int,
    *,
    limit: int = 1000,
    offset: int = 0,
) -> RegisterResponse:
    acc = db.get(Account, account_id)
    if not acc:
        raise ValueError("Account not found")

    if _is_investment_subtype(acc.subtype):
        from app.config import get_settings
        from app.services.holdings import refresh_live_investment_values

        if get_settings().live_market_quotes_enabled:
            refresh_live_investment_values(db)

    q = (
        db.query(Transaction)
        .join(Transaction.entries)
        .filter(Entry.account_id == account_id, Transaction.voided_at.is_(None))
        .options(joinedload(Transaction.entries))
    )
    if acc.tracking_start_date:
        q = q.filter(Transaction.txn_date >= acc.tracking_start_date)

    txns = q.order_by(Transaction.txn_date.asc(), Transaction.id.asc()).all()

    opening = Decimal("0")
    if acc.tracking_start_date:
        opening_txn = (
            db.query(Transaction)
            .filter(Transaction.external_id == f"opening:{account_id}")
            .first()
        )
        if opening_txn:
            entry = next(
                (e for e in opening_txn.entries if e.account_id == account_id), None
            )
            if entry:
                opening = Decimal(str(entry.amount))
        else:
            opening = account_balance(
                db, account_id, acc.tracking_start_date - timedelta(days=1)
            )

    pending_rows: list[_PendingRegisterRow] = []
    running = opening
    for txn in txns:
        ext = txn.external_id or ""
        if ext.startswith(OPENING_PREFIX):
            continue
        entry = next((e for e in txn.entries if e.account_id == account_id), None)
        if not entry:
            continue
        amt = Decimal(str(entry.amount))
        running += amt
        charge, payment = _charge_payment(amt, acc.subtype)
        cat_id, cat_name = _category_for_row(db, txn, account_id)

        recognized = recognize_transaction(
            payee=txn.payee or "",
            memo=txn.memo,
            amount=amt,
            account_subtype=acc.subtype.value,
            investment_type=txn.investment_type,
            investment_subtype=txn.investment_subtype,
            security_name=txn.security_name,
            is_transfer=txn.is_transfer,
            charge=charge,
            payment=payment,
        )

        label = activity_label_from_recognition(recognized)
        if ext.startswith(BASELINE_PREFIX) and "contribution" in ext:
            label = "Opening contribution"
        elif ext.startswith(BASELINE_PREFIX) and "buy:" in ext:
            label = f"Opening position {txn.security_name or ''}".strip()

        direction = recognized.direction
        direction_val = None if direction == "none" else direction

        pending_rows.append(
            _PendingRegisterRow(
                entry=entry,
                txn=txn,
                txn_date=txn.txn_date,
                payee=txn.payee,
                memo=txn.memo,
                charge=charge,
                payment=payment,
                running_balance=running,
                category_id=cat_id,
                category_name=cat_name,
                recognized=recognized,
                activity_label=label,
                cash_direction=direction_val,
                is_cleared=entry.is_cleared,
                is_transfer=txn.is_transfer,
                investment_type=txn.investment_type,
                investment_subtype=txn.investment_subtype,
                security_name=txn.security_name,
                quantity=txn.quantity,
                price=txn.price,
            )
        )

    _resolve_categories(db, pending_rows, account_subtype=acc.subtype.value)

    pattern_categories: dict[str, set[int]] = defaultdict(set)
    for row in pending_rows:
        if row.category_id:
            pattern_categories[_row_conflict_key(row)].add(row.category_id)

    rows: list[RegisterRow] = []
    for pending in pending_rows:
        suggestions, conflict, remember_pattern = _finalize_row_metadata(
            db,
            pending,
            pattern_categories,
            account_subtype=acc.subtype.value,
        )
        rows.append(
            RegisterRow(
                entry_id=pending.entry.id,
                transaction_id=pending.txn.id,
                txn_date=pending.txn_date,
                payee=pending.payee,
                memo=pending.memo,
                charge=pending.charge,
                payment=pending.payment,
                running_balance=pending.running_balance,
                category_id=pending.category_id,
                category_name=pending.category_name,
                category_suggestions=suggestions,
                remember_pattern=remember_pattern,
                category_conflict=conflict,
                activity_label=pending.activity_label,
                cash_direction=pending.cash_direction,
                is_cleared=pending.is_cleared,
                is_transfer=pending.is_transfer,
                source=pending.txn.source.value,
                investment_type=pending.investment_type,
                investment_subtype=pending.investment_subtype,
                security_name=pending.security_name,
                quantity=pending.quantity,
                price=pending.price,
            )
        )

    total = len(rows)
    page = rows[offset : offset + limit]

    uncleared_count = sum(1 for r in rows if not r.is_cleared)
    cleared_delta = sum(
        (r.payment or Decimal("0")) - (r.charge or Decimal("0"))
        for r in rows
        if r.is_cleared
    )
    uncleared_delta = sum(
        (r.payment or Decimal("0")) - (r.charge or Decimal("0"))
        for r in rows
        if not r.is_cleared
    )

    plaid_acct = db.query(PlaidAccount).filter(PlaidAccount.account_id == account_id).first()
    plaid_balance = (
        Decimal(str(plaid_acct.balance_current))
        if plaid_acct and plaid_acct.balance_current is not None
        else None
    )

    out_label, in_label, balance_label = register_column_labels(acc.subtype.value)

    cash_bal: Decimal | None = None
    port_val: Decimal | None = None
    holdings_list: list[HoldingSummary] = []
    holdings_as_of: date | None = None
    if _is_investment_subtype(acc.subtype):
        cash_bal, port_val = portfolio_value(db, account_id)
        holdings_list = [
            HoldingSummary(
                ticker=h.ticker,
                security_name=h.security_name,
                quantity=h.quantity,
                cost_basis_total=h.cost_basis_total,
                market_value=h.market_value,
                gain=h.gain,
            )
            for h in list_holdings(db, account_id)
        ]
        holding_dates = [
            h.as_of_date
            for h in db.query(Holding)
            .filter(Holding.account_id == account_id, Holding.as_of_date.isnot(None))
            .all()
        ]
        mark = (
            db.query(AccountMark)
            .filter(AccountMark.account_id == account_id)
            .order_by(AccountMark.as_of_date.desc())
            .first()
        )
        candidates = [d for d in holding_dates if d]
        if mark:
            candidates.append(mark.as_of_date)
        holdings_as_of = max(candidates) if candidates else None

    display_balance = port_val if port_val is not None else running

    return RegisterResponse(
        account_id=account_id,
        account_name=acc.name,
        account_subtype=acc.subtype.value,
        amount_out_label=out_label,
        amount_in_label=in_label,
        balance_column_label=balance_label,
        tracking_start_date=acc.tracking_start_date,
        opening_balance=opening,
        current_balance=display_balance,
        cash_balance=cash_bal,
        portfolio_value=port_val,
        holdings=holdings_list,
        holdings_as_of_date=holdings_as_of,
        cleared_balance=opening + cleared_delta,
        uncleared_balance=opening + uncleared_delta,
        uncleared_count=uncleared_count,
        plaid_balance_current=plaid_balance,
        total_count=total,
        rows=page,
    )


def _exclude_system_txns_filter():
    return or_(
        Transaction.external_id.is_(None),
        and_(
            ~Transaction.external_id.startswith(OPENING_PREFIX),
            ~Transaction.external_id.startswith(BASELINE_PREFIX),
        ),
    )


def _pending_staging_count(db: Session, account_id: int) -> int:
    plaid_ids = [
        row[0]
        for row in db.query(PlaidAccount.id)
        .filter(PlaidAccount.account_id == account_id)
        .all()
    ]
    if not plaid_ids:
        return 0
    return (
        db.scalar(
            select(func.count())
            .select_from(ImportStaging)
            .where(
                ImportStaging.plaid_account_id.in_(plaid_ids),
                ImportStaging.status == StagingStatus.pending,
            )
        )
        or 0
    )


def account_register_pending_count(db: Session, account_id: int) -> int:
    """Uncleared register rows and unstaged Plaid imports still needing attention."""
    acc = db.get(Account, account_id)
    if not acc:
        return 0

    tracking = acc.tracking_start_date
    uncleared_q = (
        select(func.count())
        .select_from(Entry)
        .join(Transaction, Entry.transaction_id == Transaction.id)
        .where(
            Entry.account_id == account_id,
            Entry.is_cleared.is_(False),
            Transaction.voided_at.is_(None),
            _exclude_system_txns_filter(),
        )
    )
    if tracking:
        uncleared_q = uncleared_q.where(Transaction.txn_date >= tracking)
    uncleared = db.scalar(uncleared_q) or 0

    return int(uncleared) + _pending_staging_count(db, account_id)
