"""Explain ledger vs Plaid balance differences for an account."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.account import Account, AccountSubtype
from app.models.entry import Entry
from app.models.plaid import PlaidAccount
from app.models.transaction import Transaction
from app.services.ledger import account_balance
from app.services.plaid_dedup import OPENING_PREFIX


def explain_balance(db: Session, account_id: int) -> dict[str, Any]:
    acc = db.get(Account, account_id)
    if not acc:
        raise ValueError("Account not found")

    ledger_balance = account_balance(db, account_id)
    plaid_acct = db.query(PlaidAccount).filter(PlaidAccount.account_id == account_id).first()
    plaid_balance = (
        Decimal(str(plaid_acct.balance_current))
        if plaid_acct and plaid_acct.balance_current is not None
        else None
    )

    txns = (
        db.query(Transaction)
        .options(joinedload(Transaction.entries))
        .filter(Transaction.voided_at.is_(None))
        .all()
    )
    uncleared_total = Decimal("0")
    uncleared_count = 0
    for txn in txns:
        for entry in txn.entries:
            if entry.account_id != account_id:
                continue
            if not entry.is_cleared:
                uncleared_total += Decimal(str(entry.amount))
                uncleared_count += 1

    opening_balance = Decimal("0")
    for txn in txns:
        if (txn.external_id or "").startswith(OPENING_PREFIX):
            for entry in txn.entries:
                if entry.account_id == account_id:
                    opening_balance = Decimal(str(entry.amount))

    recent_voids: list[dict[str, str]] = []
    cutoff = date.today() - timedelta(days=30)
    voided = (
        db.query(Transaction)
        .options(joinedload(Transaction.entries))
        .filter(Transaction.voided_at.isnot(None), Transaction.txn_date >= cutoff)
        .order_by(Transaction.voided_at.desc())
        .limit(10)
        .all()
    )
    for txn in voided:
        for entry in txn.entries:
            if entry.account_id == account_id:
                recent_voids.append(
                    {
                        "transaction_id": str(txn.id),
                        "txn_date": txn.txn_date.isoformat(),
                        "payee": txn.payee or "",
                        "amount": str(entry.amount),
                    }
                )

    cross_post_candidates: list[dict[str, str]] = []
    if acc.subtype == AccountSubtype.checking:
        from app.services.card_payments import resolve_card_account_from_payment

        for txn in txns:
            if txn.txn_date < date.today() - timedelta(days=14):
                continue
            card = resolve_card_account_from_payment(db, txn.payee or "")
            if card:
                for entry in txn.entries:
                    if entry.account_id == account_id and entry.amount < 0:
                        cross_post_candidates.append(
                            {
                                "transaction_id": str(txn.id),
                                "txn_date": txn.txn_date.isoformat(),
                                "payee": txn.payee or "",
                                "amount": str(entry.amount),
                                "suggested_card": card.name,
                            }
                        )

    delta = None
    if plaid_balance is not None:
        delta = ledger_balance - plaid_balance

    return {
        "account_id": account_id,
        "account_name": acc.name,
        "ledger_balance": str(ledger_balance),
        "plaid_balance": str(plaid_balance) if plaid_balance is not None else None,
        "delta": str(delta) if delta is not None else None,
        "opening_balance": str(opening_balance),
        "uncleared_total": str(uncleared_total),
        "uncleared_count": uncleared_count,
        "recent_voids": recent_voids,
        "cross_post_candidates": cross_post_candidates[:5],
        "hints": _hints(delta, uncleared_count, recent_voids),
    }


def _hints(
    delta: Decimal | None,
    uncleared_count: int,
    recent_voids: list[dict[str, str]],
) -> list[str]:
    hints: list[str] = []
    if delta is not None and abs(delta) >= Decimal("0.02"):
        if uncleared_count:
            hints.append("Uncleared transactions may explain part of the difference.")
        if recent_voids:
            hints.append("Recent voided duplicates were removed — re-sync may have fixed this.")
        if abs(delta) > Decimal("100"):
            hints.append("Large mismatch — check duplicate review queue and opening balance.")
    elif delta is not None:
        hints.append("Ledger matches Plaid within rounding tolerance.")
    return hints
