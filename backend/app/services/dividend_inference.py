"""Infer annual dividend income per ticker from register history."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.account import Account, AccountSubtype
from app.models.transaction import Transaction
from app.services.transaction_recognition import recognize_transaction

_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")


def _extract_ticker(txn: Transaction) -> str | None:
    rec = recognize_transaction(
        payee=txn.payee,
        memo=txn.memo,
        investment_subtype=txn.investment_subtype,
    )
    if rec.ticker:
        return rec.ticker.upper()
    match = _TICKER_RE.search(txn.payee or "")
    return match.group(1) if match else None


def infer_dividends_by_ticker(db: Session, *, months: int = 12) -> dict[str, dict[str, Any]]:
    cutoff = date.today() - timedelta(days=months * 30)
    txns = (
        db.query(Transaction)
        .options(joinedload(Transaction.entries))
        .filter(Transaction.voided_at.is_(None), Transaction.txn_date >= cutoff)
        .all()
    )
    by_ticker: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    counts: dict[str, int] = defaultdict(int)
    for txn in txns:
        rec = recognize_transaction(
            payee=txn.payee,
            memo=txn.memo,
            investment_subtype=txn.investment_subtype,
        )
        if rec.family != "dividend":
            continue
        ticker = _extract_ticker(txn)
        if not ticker:
            continue
        amount = Decimal("0")
        for entry in txn.entries:
            amount += abs(Decimal(str(entry.amount)))
        by_ticker[ticker] += amount
        counts[ticker] += 1

    result: dict[str, dict[str, Any]] = {}
    for ticker, total in by_ticker.items():
        annualized = total * Decimal("12") / Decimal(str(months))
        confidence = "high" if counts[ticker] >= 2 else "low"
        result[ticker] = {
            "trailing_total": str(total),
            "annualized": str(annualized.quantize(Decimal("0.01"))),
            "payment_count": counts[ticker],
            "confidence": confidence,
        }
    return result


def infer_dividends_for_account(db: Session, account_id: int, *, months: int = 12) -> dict[str, Any]:
    acc = db.get(Account, account_id)
    if not acc:
        raise ValueError("Account not found")
    cutoff = date.today() - timedelta(days=months * 30)
    txns = (
        db.query(Transaction)
        .options(joinedload(Transaction.entries))
        .filter(
            Transaction.voided_at.is_(None),
            Transaction.txn_date >= cutoff,
        )
        .all()
    )
    total = Decimal("0")
    for txn in txns:
        if not any(e.account_id == account_id for e in txn.entries):
            continue
        rec = recognize_transaction(
            payee=txn.payee,
            memo=txn.memo,
            investment_subtype=txn.investment_subtype,
        )
        if rec.family != "dividend":
            continue
        for entry in txn.entries:
            if entry.account_id == account_id:
                total += abs(Decimal(str(entry.amount)))
    annualized = total * Decimal("12") / Decimal(str(months))
    return {
        "account_id": account_id,
        "trailing_total": str(total),
        "annualized": str(annualized.quantize(Decimal("0.01"))),
    }
