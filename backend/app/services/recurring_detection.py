"""Detect recurring transactions from payee patterns."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.transaction import Transaction


def detect_recurring(db: Session, *, lookback_days: int = 180) -> list[dict[str, Any]]:
    cutoff = date.today() - timedelta(days=lookback_days)
    txns = (
        db.query(Transaction)
        .options(joinedload(Transaction.entries))
        .filter(Transaction.voided_at.is_(None), Transaction.txn_date >= cutoff)
        .all()
    )
    by_payee: dict[str, list[Transaction]] = defaultdict(list)
    for txn in txns:
        key = (txn.payee or "").strip().upper()
        if len(key) < 4:
            continue
        by_payee[key].append(txn)

    recurring: list[dict[str, Any]] = []
    for payee, group in by_payee.items():
        if len(group) < 3:
            continue
        dates = sorted(t.txn_date for t in group)
        gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        if not gaps:
            continue
        avg_gap = sum(gaps) / len(gaps)
        if 25 <= avg_gap <= 35 or 12 <= avg_gap <= 16:
            amounts = []
            for t in group:
                for e in t.entries:
                    amounts.append(abs(Decimal(str(e.amount))))
            typical = sum(amounts) / len(amounts) if amounts else Decimal("0")
            next_est = dates[-1] + timedelta(days=int(avg_gap))
            recurring.append(
                {
                    "payee": payee,
                    "occurrences": len(group),
                    "avg_interval_days": round(avg_gap, 1),
                    "typical_amount": str(typical.quantize(Decimal("0.01"))),
                    "last_date": dates[-1].isoformat(),
                    "next_estimated": next_est.isoformat(),
                }
            )
    recurring.sort(key=lambda r: r["next_estimated"])
    return recurring[:20]
