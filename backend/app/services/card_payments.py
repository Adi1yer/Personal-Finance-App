from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.account import Account, AccountSubtype, AccountType
from app.models.plaid import PlaidAccount
from app.models.transaction import Transaction, TransactionSource
from app.services.categorization import is_card_payment, parse_plaid_raw

_CARD_MASK_RE = re.compile(r"ending in (\d{4})", re.I)
CARD_PAYMENT_DATE_TOLERANCE_DAYS = 3


def resolve_card_account_from_payment(db: Session, payee: str) -> Account | None:
    match = _CARD_MASK_RE.search(payee)
    if not match:
        return None
    mask = match.group(1)
    plaid_acct = (
        db.query(PlaidAccount)
        .filter(PlaidAccount.mask == mask, PlaidAccount.account_id.isnot(None))
        .first()
    )
    if not plaid_acct or not plaid_acct.account_id:
        return None
    acc = db.get(Account, plaid_acct.account_id)
    if acc and acc.subtype == AccountSubtype.credit_card:
        return acc
    return None


def find_card_payment_txn(
    db: Session,
    txn_date: date,
    amount: Decimal,
    card_account_id: int | None = None,
    *,
    date_tolerance_days: int = 0,
) -> Transaction | None:
    """Find an existing checking+card payment (no expense leg) for the same amount."""
    target = abs(Decimal(str(amount)))
    start = txn_date - timedelta(days=date_tolerance_days)
    end = txn_date + timedelta(days=date_tolerance_days)
    txns = (
        db.query(Transaction)
        .filter(
            Transaction.voided_at.is_(None),
            Transaction.txn_date >= start,
            Transaction.txn_date <= end,
        )
        .all()
    )
    for txn in txns:
        checking_amt = None
        card_id = None
        card_amt = None
        has_expense = False
        for entry in txn.entries:
            acc = db.get(Account, entry.account_id)
            if not acc:
                continue
            if acc.subtype == AccountSubtype.checking:
                checking_amt = entry.amount
            elif acc.subtype == AccountSubtype.credit_card:
                card_id = acc.id
                card_amt = entry.amount
            elif acc.account_type in (AccountType.expense, AccountType.income):
                has_expense = True
        if checking_amt is None or card_amt is None or has_expense:
            continue
        if card_account_id and card_id != card_account_id:
            continue
        if abs(checking_amt) == target and abs(card_amt) == target:
            return txn
    return None


def _is_checking_only_card_payment(db: Session, txn: Transaction) -> bool:
    checking_amt = None
    has_card = False
    has_expense = False
    staging = None
    if txn.external_id:
        from app.models.import_staging import ImportStaging

        staging = (
            db.query(ImportStaging)
            .filter(ImportStaging.external_id == txn.external_id)
            .first()
        )
    raw = parse_plaid_raw(staging.raw_json if staging else None)
    plaid_amount = float(raw.get("amount", checking_amt or 0))
    if not is_card_payment(raw, plaid_amount, payee=txn.payee or ""):
        return False
    for entry in txn.entries:
        acc = db.get(Account, entry.account_id)
        if not acc:
            continue
        if acc.subtype == AccountSubtype.checking:
            checking_amt = entry.amount
        elif acc.subtype == AccountSubtype.credit_card:
            has_card = True
        elif acc.account_type in (AccountType.expense, AccountType.income):
            has_expense = True
    return checking_amt is not None and has_expense and not has_card


def repair_duplicate_card_payments(db: Session) -> dict[str, int]:
    """
    Void checking-side card payments that duplicate an existing checking+card payment.
    """
    voided = 0
    txns = (
        db.query(Transaction)
        .filter(
            Transaction.source == TransactionSource.plaid,
            Transaction.voided_at.is_(None),
        )
        .all()
    )
    for txn in txns:
        if not _is_checking_only_card_payment(db, txn):
            continue
        checking_amt = next(
            e.amount
            for e in txn.entries
            if db.get(Account, e.account_id)
            and db.get(Account, e.account_id).subtype == AccountSubtype.checking
        )
        card = resolve_card_account_from_payment(db, txn.payee or "")
        existing = find_card_payment_txn(
            db,
            txn.txn_date,
            checking_amt,
            card.id if card else None,
            date_tolerance_days=CARD_PAYMENT_DATE_TOLERANCE_DAYS,
        )
        if not existing:
            continue
        txn.voided_at = datetime.now(timezone.utc)
        if txn.external_id:
            txn.external_id = None
        voided += 1
    if voided:
        db.commit()

    from app.services.opening_balances import seed_opening_balances

    opening = seed_opening_balances(db) if voided else {"updated": 0, "created": 0}
    return {"voided": voided, "opening_updated": opening.get("updated", 0)}
