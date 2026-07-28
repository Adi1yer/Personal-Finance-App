from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.account import Account, AccountSubtype, AccountType
from app.models.entry import Entry
from app.models.plaid import PlaidAccount
from app.models.transaction import Transaction, TransactionSource
from app.schemas.transaction import EntryLine, TransactionCreate
from app.services.posting import create_transaction
from app.services.seed import DEFAULT_TRACKING_START

OPENING_EXTERNAL_PREFIX = "opening:"


def net_entry_change_since_tracking(
    db: Session, account_id: int, tracking_start: date
) -> Decimal:
    """Sum of entry amounts on/after tracking_start, excluding opening-balance txns."""
    rows = (
        db.query(Entry)
        .join(Transaction)
        .filter(
            Entry.account_id == account_id,
            Transaction.voided_at.is_(None),
            Transaction.txn_date >= tracking_start,
        )
        .all()
    )
    total = Decimal("0")
    for entry in rows:
        txn = entry.transaction
        if txn.external_id and txn.external_id.startswith(OPENING_EXTERNAL_PREFIX):
            continue
        total += Decimal(str(entry.amount))
    return total


def compute_opening_entry_amount(
    account_type: AccountType,
    plaid_balance: Decimal,
    net_change: Decimal,
) -> Decimal:
    """Entry amount for the tracked account's opening-balance transaction."""
    if account_type == AccountType.asset:
        return plaid_balance - net_change
    if account_type == AccountType.liability:
        return -plaid_balance - net_change
    return Decimal("0")


def _upsert_opening_balance(
    db: Session,
    acc: Account,
    equity: Account,
    opening_amount: Decimal,
) -> str:
    external_id = f"{OPENING_EXTERNAL_PREFIX}{acc.id}"
    existing = (
        db.query(Transaction).filter(Transaction.external_id == external_id).first()
    )

    txn_date = acc.tracking_start_date or DEFAULT_TRACKING_START

    if existing:
        existing.txn_date = txn_date
        for entry in existing.entries:
            if entry.account_id == acc.id:
                entry.amount = opening_amount
            elif entry.account_id == equity.id:
                entry.amount = -opening_amount
        db.commit()
        return "updated"

    if opening_amount == 0:
        return "skipped"

    create_transaction(
        db,
        TransactionCreate(
            txn_date=txn_date,
            payee="Opening balance",
            memo="Tracking start balance",
            external_id=external_id,
            entries=[
                EntryLine(account_id=acc.id, amount=opening_amount),
                EntryLine(account_id=equity.id, amount=-opening_amount),
            ],
        ),
        source=TransactionSource.manual,
    )
    return "created"


def seed_opening_balances(db: Session) -> dict[str, int]:
    """Create or update tracking-start opening entries so ledger matches Plaid current balance."""
    created = updated = skipped = 0
    equity = db.query(Account).filter(Account.slug == "opening_equity").first()
    if not equity:
        return {"created": 0, "updated": 0, "skipped": 0, "error": "missing opening_equity account"}

    accounts = (
        db.query(Account)
        .filter(
            Account.tracking_start_date.isnot(None),
            Account.subtype.in_([AccountSubtype.checking, AccountSubtype.credit_card]),
            Account.is_active.is_(True),
        )
        .all()
    )

    for acc in accounts:
        tracking_start = acc.tracking_start_date
        if not tracking_start:
            skipped += 1
            continue

        plaid_acct = (
            db.query(PlaidAccount).filter(PlaidAccount.account_id == acc.id).first()
        )
        if not plaid_acct or plaid_acct.balance_current is None:
            skipped += 1
            continue

        plaid_balance = Decimal(str(plaid_acct.balance_current))
        net_change = net_entry_change_since_tracking(db, acc.id, tracking_start)
        opening_amount = compute_opening_entry_amount(
            acc.account_type, plaid_balance, net_change
        )

        result = _upsert_opening_balance(db, acc, equity, opening_amount)
        if result == "created":
            created += 1
        elif result == "updated":
            updated += 1
        else:
            skipped += 1

    return {"created": created, "updated": updated, "skipped": skipped}


def repair_opening_balances(db: Session) -> dict[str, int]:
    """Recompute all opening:* entries from current Plaid balances (one-time repair)."""
    return seed_opening_balances(db)
