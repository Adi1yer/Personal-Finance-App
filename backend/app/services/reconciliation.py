from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from app.models.account import Account, AccountSubtype
from app.models.entry import Entry
from app.models.transaction import Transaction
from app.schemas.reconciliation import ReconciliationCreate
from app.services.ledger import account_balance
from app.services.register import get_register


def create_reconciliation(
    db: Session, account_id: int, data: ReconciliationCreate
) -> "Reconciliation":
    from app.models.reconciliation import Reconciliation, ReconciliationEntry

    rec = Reconciliation(
        account_id=account_id,
        statement_end_date=data.statement_end_date,
        ending_balance=data.ending_balance,
    )
    db.add(rec)
    db.flush()

    for entry_id in data.cleared_entry_ids:
        entry = db.get(Entry, entry_id)
        if entry and entry.account_id == account_id:
            entry.is_cleared = True
            db.add(ReconciliationEntry(reconciliation_id=rec.id, entry_id=entry_id))

    db.commit()
    db.refresh(rec)
    return rec


def reconciliation_preview(
    db: Session,
    account_id: int,
    statement_end_date: date,
    ending_balance: Decimal,
) -> dict:
    acc = db.get(Account, account_id)
    if not acc:
        raise ValueError("Account not found")

    reg = get_register(db, account_id, limit=5000)
    uncleared = [r for r in reg.rows if not r.is_cleared and r.txn_date <= statement_end_date]
    cleared = [r for r in reg.rows if r.is_cleared and r.txn_date <= statement_end_date]

    def _row_delta(r) -> Decimal:
        return Decimal(str(r.payment or 0)) - Decimal(str(r.charge or 0))

    cleared_txn_sum = sum((_row_delta(r) for r in cleared), Decimal("0"))
    cleared_balance = reg.opening_balance + cleared_txn_sum
    ledger_balance = account_balance(db, account_id, statement_end_date)
    difference = ending_balance - cleared_balance

    return {
        "account_id": account_id,
        "statement_end_date": statement_end_date.isoformat(),
        "ending_balance": str(ending_balance),
        "opening_balance": str(reg.opening_balance),
        "ledger_balance": str(ledger_balance),
        "cleared_balance": str(cleared_balance),
        "difference": str(difference),
        "uncleared_entries": [
            {
                "entry_id": r.entry_id,
                "txn_date": r.txn_date.isoformat(),
                "payee": r.payee,
                "charge": str(r.charge) if r.charge else None,
                "payment": str(r.payment) if r.payment else None,
            }
            for r in uncleared
        ],
    }


def reconciliation_status(
    db: Session, account_id: int, statement_balance: Decimal
) -> dict:
    balance = account_balance(db, account_id)
    cleared_q = (
        db.query(Entry)
        .filter(Entry.account_id == account_id, Entry.is_cleared.is_(True))
    )
    cleared_sum = sum((e.amount for e in cleared_q.all()), Decimal("0"))
    return {
        "ledger_balance": balance,
        "statement_balance": statement_balance,
        "difference": balance - statement_balance,
        "cleared_entry_count": cleared_q.count(),
    }
