"""Detect and repair duplicate Plaid transactions (pending→posted ID/date changes)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.entry import Entry
from app.models.import_staging import ImportStaging, StagingStatus
from app.models.plaid import PlaidAccount
from app.models.transaction import Transaction, TransactionSource
from app.services.payee_normalization import parse_venmo, parse_zelle, strip_trailing_id

PENDING_POSTED_DATE_TOLERANCE_DAYS = 7
OPENING_PREFIX = "opening:"
BASELINE_PREFIX = "baseline:"


def normalize_plaid_payee_key(payee: str) -> str:
    zelle = parse_zelle(payee)
    if zelle:
        return zelle.canonical.upper()
    venmo = parse_venmo(payee)
    if venmo:
        return f"VENMO {venmo.upper()}"
    return strip_trailing_id(payee).strip().upper()


def _amount_key(amount: Decimal) -> Decimal:
    return abs(Decimal(str(amount))).quantize(Decimal("0.01"))


def _is_system_txn(txn: Transaction) -> bool:
    ext = txn.external_id or ""
    return ext.startswith(OPENING_PREFIX) or ext.startswith(BASELINE_PREFIX)


def _pair_rank(txn: Transaction, entry: Entry) -> tuple[int, int, int]:
    return (1 if entry.is_cleared else 0, txn.txn_date.toordinal(), txn.id)


def _entry_for_account(txn: Transaction, account_id: int) -> Entry | None:
    return next((e for e in txn.entries if e.account_id == account_id), None)


def _matches_activity(
    txn: Transaction,
    entry: Entry,
    account_id: int,
    payee_key: str,
    target_amt: Decimal,
) -> bool:
    if entry.account_id != account_id:
        return False
    if _is_system_txn(txn):
        return False
    if normalize_plaid_payee_key(txn.payee or "") != payee_key:
        return False
    return _amount_key(entry.amount) == target_amt


def _mark_staging_skipped_for_txn(db: Session, txn: Transaction) -> None:
    if not txn.external_id:
        return
    for row in db.query(ImportStaging).filter(ImportStaging.external_id == txn.external_id).all():
        row.status = StagingStatus.skipped


def _cluster_by_date(
    pairs: list[tuple[Transaction, Entry]], tolerance_days: int
) -> list[list[tuple[Transaction, Entry]]]:
    if not pairs:
        return []
    sorted_pairs = sorted(pairs, key=lambda p: (p[0].txn_date, p[0].id))
    clusters: list[list[tuple[Transaction, Entry]]] = []
    current = [sorted_pairs[0]]
    for pair in sorted_pairs[1:]:
        delta = (pair[0].txn_date - current[-1][0].txn_date).days
        if delta <= tolerance_days:
            current.append(pair)
        else:
            clusters.append(current)
            current = [pair]
    clusters.append(current)
    return clusters


def find_pending_staging_duplicate(
    db: Session,
    account_id: int,
    payee: str,
    amount: Decimal,
    txn_date: date,
    *,
    exclude_staging_id: int | None = None,
    exclude_external_id: str | None = None,
) -> ImportStaging | None:
    """Return a pending staging row that looks like the same Plaid activity."""
    payee_key = normalize_plaid_payee_key(payee)
    target_amt = _amount_key(amount)
    start = txn_date - timedelta(days=PENDING_POSTED_DATE_TOLERANCE_DAYS)
    end = txn_date + timedelta(days=PENDING_POSTED_DATE_TOLERANCE_DAYS)

    rows = (
        db.query(ImportStaging)
        .join(PlaidAccount, ImportStaging.plaid_account_id == PlaidAccount.id)
        .filter(
            ImportStaging.status == StagingStatus.pending,
            PlaidAccount.account_id == account_id,
            ImportStaging.txn_date >= start,
            ImportStaging.txn_date <= end,
        )
        .order_by(ImportStaging.txn_date.asc(), ImportStaging.id.asc())
        .all()
    )
    for row in rows:
        if exclude_staging_id and row.id == exclude_staging_id:
            continue
        if exclude_external_id and row.external_id == exclude_external_id:
            continue
        if normalize_plaid_payee_key(row.payee or "") != payee_key:
            continue
        if _amount_key(row.amount) != target_amt:
            continue
        return row
    return None


def find_recorded_plaid_activity(
    db: Session,
    account_id: int,
    payee: str,
    amount: Decimal,
    txn_date: date,
    *,
    include_voided: bool = True,
    exclude_txn_id: int | None = None,
) -> Transaction | None:
    """Return a ledger row (active or voided) that already recorded this Plaid activity."""
    payee_key = normalize_plaid_payee_key(payee)
    target_amt = _amount_key(amount)
    start = txn_date - timedelta(days=PENDING_POSTED_DATE_TOLERANCE_DAYS)
    end = txn_date + timedelta(days=PENDING_POSTED_DATE_TOLERANCE_DAYS)

    q = (
        db.query(Transaction)
        .join(Entry)
        .filter(
            Entry.account_id == account_id,
            Transaction.source == TransactionSource.plaid,
            Transaction.txn_date >= start,
            Transaction.txn_date <= end,
        )
    )
    if not include_voided:
        q = q.filter(Transaction.voided_at.is_(None))

    matches: list[tuple[Transaction, Entry]] = []
    for txn in q.order_by(Transaction.txn_date.asc(), Transaction.id.asc()).all():
        if exclude_txn_id and txn.id == exclude_txn_id:
            continue
        entry = _entry_for_account(txn, account_id)
        if not entry:
            continue
        if _matches_activity(txn, entry, account_id, payee_key, target_amt):
            matches.append((txn, entry))

    if not matches:
        return None
    return max(matches, key=lambda pair: _pair_rank(pair[0], pair[1]))[0]


def staging_already_satisfied(db: Session, row: ImportStaging) -> bool:
    """True when this Plaid import was already handled on the ledger."""
    if row.external_id:
        existing = (
            db.query(Transaction)
            .filter(
                Transaction.external_id == row.external_id,
                Transaction.voided_at.is_(None),
            )
            .first()
        )
        if existing:
            return True
    return staging_has_live_ledger_match(db, row)


def staging_has_live_ledger_match(db: Session, row: ImportStaging) -> bool:
    """True when an active ledger row already represents this staging activity."""
    if not row.plaid_account_id:
        return False
    plaid_acct = db.get(PlaidAccount, row.plaid_account_id)
    if not plaid_acct or not plaid_acct.account_id:
        return False
    return (
        find_semantic_duplicate(
            db,
            plaid_acct.account_id,
            row.payee,
            row.amount,
            row.txn_date,
        )
        is not None
    )


def find_semantic_duplicate(
    db: Session,
    account_id: int,
    payee: str,
    amount: Decimal,
    txn_date: date,
    *,
    exclude_txn_id: int | None = None,
) -> Transaction | None:
    """Return an active ledger transaction that looks like the same Plaid activity."""
    payee_key = normalize_plaid_payee_key(payee)
    target_amt = _amount_key(amount)
    start = txn_date - timedelta(days=PENDING_POSTED_DATE_TOLERANCE_DAYS)
    end = txn_date + timedelta(days=PENDING_POSTED_DATE_TOLERANCE_DAYS)

    txns = (
        db.query(Transaction)
        .join(Entry)
        .filter(
            Entry.account_id == account_id,
            Transaction.voided_at.is_(None),
            Transaction.txn_date >= start,
            Transaction.txn_date <= end,
        )
        .order_by(Transaction.txn_date.asc(), Transaction.id.asc())
        .all()
    )

    matches: list[Transaction] = []
    for txn in txns:
        if exclude_txn_id and txn.id == exclude_txn_id:
            continue
        if _is_system_txn(txn):
            continue
        if normalize_plaid_payee_key(txn.payee or "") != payee_key:
            continue
        entry = next((e for e in txn.entries if e.account_id == account_id), None)
        if not entry or _amount_key(entry.amount) != target_amt:
            continue
        matches.append(txn)

    if not matches:
        return None
    best = max(
        ((txn, next(e for e in txn.entries if e.account_id == account_id)) for txn in matches),
        key=lambda pair: _pair_rank(pair[0], pair[1]),
    )
    return best[0]


def find_plaid_activity_duplicate(
    db: Session,
    account_id: int,
    payee: str,
    amount: Decimal,
    txn_date: date,
    *,
    exclude_txn_id: int | None = None,
    exclude_staging_id: int | None = None,
    exclude_external_id: str | None = None,
    include_voided_recorded: bool = False,
) -> Transaction | ImportStaging | None:
    """Return an existing ledger or in-flight staging row for the same Plaid activity."""
    txn = find_semantic_duplicate(
        db,
        account_id,
        payee,
        amount,
        txn_date,
        exclude_txn_id=exclude_txn_id,
    )
    if txn:
        return txn
    if include_voided_recorded:
        recorded = find_recorded_plaid_activity(
            db,
            account_id,
            payee,
            amount,
            txn_date,
            include_voided=True,
            exclude_txn_id=exclude_txn_id,
        )
        if recorded:
            return recorded
    return find_pending_staging_duplicate(
        db,
        account_id,
        payee,
        amount,
        txn_date,
        exclude_staging_id=exclude_staging_id,
        exclude_external_id=exclude_external_id,
    )


def _void_duplicate_txn(db: Session, txn: Transaction) -> None:
    _mark_staging_skipped_for_txn(db, txn)
    txn.voided_at = datetime.now(timezone.utc)
    if txn.external_id:
        txn.external_id = None


def _restore_voided_cluster_keepers(db: Session, freshly_voided_ids: set[int]) -> int:
    """If this repair pass voided every copy in a cluster, restore the best keeper."""
    if not freshly_voided_ids:
        return 0
    restored = 0
    accounts = db.query(Account).filter(Account.is_active.is_(True)).all()

    for acc in accounts:
        txns = (
            db.query(Transaction)
            .join(Entry)
            .filter(
                Entry.account_id == acc.id,
                Transaction.source == TransactionSource.plaid,
            )
            .order_by(Transaction.txn_date.asc(), Transaction.id.asc())
            .all()
        )
        by_key: dict[tuple[str, Decimal], list[tuple[Transaction, Entry]]] = defaultdict(list)
        for txn in txns:
            if _is_system_txn(txn):
                continue
            entry = _entry_for_account(txn, acc.id)
            if not entry:
                continue
            key = (normalize_plaid_payee_key(txn.payee or ""), _amount_key(entry.amount))
            by_key[key].append((txn, entry))

        for group in by_key.values():
            if any(not txn.voided_at for txn, _entry in group):
                continue
            if not any(txn.id in freshly_voided_ids for txn, _entry in group):
                continue
            for cluster in _cluster_by_date(group, PENDING_POSTED_DATE_TOLERANCE_DAYS):
                if any(not txn.voided_at for txn, _entry in cluster):
                    continue
                if not any(txn.id in freshly_voided_ids for txn, _entry in cluster):
                    continue
                keeper = max(cluster, key=lambda pair: _pair_rank(pair[0], pair[1]))
                keeper[0].voided_at = None
                restored += 1

    if restored:
        db.commit()
    return restored


def cleanup_satisfied_staging(db: Session) -> dict[str, int]:
    """Mark staging rows skipped when their activity is already recorded."""
    skipped = 0
    for row in db.query(ImportStaging).filter(
        ImportStaging.status.in_([StagingStatus.pending, StagingStatus.posted])
    ).all():
        if staging_already_satisfied(db, row):
            row.status = StagingStatus.skipped
            skipped += 1
    if skipped:
        db.commit()
    return {"skipped": skipped}


def repair_duplicate_plaid_transactions(db: Session) -> dict[str, int]:
    """
    Void duplicate Plaid rows caused by pending→posted transaction_id and date changes.
    Keeps the cleared / latest copy.
    """
    voided = 0
    freshly_voided_ids: set[int] = set()
    accounts = db.query(Account).filter(Account.is_active.is_(True)).all()

    for acc in accounts:
        txns = (
            db.query(Transaction)
            .join(Entry)
            .filter(Entry.account_id == acc.id, Transaction.voided_at.is_(None))
            .order_by(Transaction.txn_date.asc(), Transaction.id.asc())
            .all()
        )
        by_key: dict[tuple[str, Decimal], list[tuple[Transaction, Entry]]] = defaultdict(list)
        for txn in txns:
            if _is_system_txn(txn):
                continue
            entry = next((e for e in txn.entries if e.account_id == acc.id), None)
            if not entry:
                continue
            key = (normalize_plaid_payee_key(txn.payee or ""), _amount_key(entry.amount))
            by_key[key].append((txn, entry))

        for group in by_key.values():
            if len(group) < 2:
                continue
            for cluster in _cluster_by_date(group, PENDING_POSTED_DATE_TOLERANCE_DAYS):
                if len(cluster) < 2:
                    continue
                keeper = max(cluster, key=lambda pair: _pair_rank(pair[0], pair[1]))
                for txn, _entry in cluster:
                    if txn.id == keeper[0].id:
                        continue
                    _void_duplicate_txn(db, txn)
                    freshly_voided_ids.add(txn.id)
                    voided += 1

    if voided:
        db.commit()

    restored = _restore_voided_cluster_keepers(db, freshly_voided_ids)
    staging = cleanup_satisfied_staging(db)

    from app.services.opening_balances import seed_opening_balances

    opening = seed_opening_balances(db) if voided or restored else {"updated": 0, "created": 0}
    return {
        "voided": voided,
        "restored": restored,
        "staging_skipped": staging.get("skipped", 0),
        "opening_updated": opening.get("updated", 0),
    }
