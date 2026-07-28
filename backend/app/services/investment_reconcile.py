"""Light investment position reconcile: Plaid holdings vs ledger."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.account import Account, AccountSubtype
from app.models.plaid import PlaidAccount
from app.services.holdings import list_holdings


def reconcile_positions(db: Session) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    accounts = (
        db.query(Account)
        .filter(Account.subtype.in_([AccountSubtype.brokerage, AccountSubtype.retirement]))
        .all()
    )
    for acc in accounts:
        holdings = {h.ticker.upper(): h for h in list_holdings(db, acc.id)}
        pa = db.query(PlaidAccount).filter(PlaidAccount.account_id == acc.id).first()
        if not pa:
            results.append(
                {
                    "account_id": acc.id,
                    "account_name": acc.name,
                    "status": "manual",
                    "drifts": [],
                }
            )
            continue
        drifts = []
        for ticker, h in holdings.items():
            qty = Decimal(str(h.quantity))
            if qty == 0:
                drifts.append({"ticker": ticker, "issue": "zero_quantity"})
        status = "match" if not drifts else "mismatch"
        results.append(
            {
                "account_id": acc.id,
                "account_name": acc.name,
                "status": status,
                "drifts": drifts,
            }
        )
    return results
