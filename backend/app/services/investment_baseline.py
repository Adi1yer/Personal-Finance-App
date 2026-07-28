from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.account import Account, AccountSubtype
from app.models.transaction import Transaction, TransactionSource
from app.schemas.transaction import EntryLine, TransactionCreate
from app.services.holdings import rebuild_holdings_from_transactions
from app.services.posting import create_transaction

BASELINE_PREFIX = "baseline:"
# Optional per-install baseline specs (empty by default for public releases).
# Callers may still seed opening positions via the UI / holdings sync.
BASELINE_DATE = date.today().replace(month=1, day=1)
BASELINE_MEMO = "Baseline position"


@dataclass(frozen=True)
class BaselinePosition:
    ticker: str
    security_name: str
    quantity: Decimal
    cost: Decimal


@dataclass(frozen=True)
class BaselineAccountSpec:
    name_match: str
    cash: Decimal
    positions: tuple[BaselinePosition, ...]


BASELINE_SPECS: tuple[BaselineAccountSpec, ...] = ()


def _find_account(db: Session, name_match: str) -> Account | None:
    return (
        db.query(Account)
        .filter(
            Account.name.ilike(f"%{name_match}%"),
            Account.subtype.in_([AccountSubtype.brokerage, AccountSubtype.retirement]),
            Account.is_active.is_(True),
        )
        .first()
    )


def _upsert_baseline_txn(
    db: Session,
    *,
    external_id: str,
    txn_date: date,
    payee: str,
    amount: Decimal,
    account_id: int,
    equity_id: int,
    investment_type: str | None = None,
    investment_subtype: str | None = None,
    security_name: str | None = None,
    quantity: Decimal | None = None,
    price: Decimal | None = None,
) -> str:
    existing = (
        db.query(Transaction).filter(Transaction.external_id == external_id).first()
    )
    if existing:
        for entry in existing.entries:
            if entry.account_id == account_id:
                entry.amount = amount
            elif entry.account_id == equity_id:
                entry.amount = -amount
        existing.payee = payee
        existing.txn_date = txn_date
        existing.memo = BASELINE_MEMO
        if investment_type:
            existing.investment_type = investment_type
            existing.investment_subtype = investment_subtype
            existing.security_name = security_name
            existing.quantity = quantity
            existing.price = price
        db.commit()
        return "updated"

    txn = create_transaction(
        db,
        TransactionCreate(
            txn_date=txn_date,
            payee=payee,
            memo=BASELINE_MEMO,
            external_id=external_id,
            entries=[
                EntryLine(account_id=account_id, amount=amount),
                EntryLine(account_id=equity_id, amount=-amount),
            ],
        ),
        source=TransactionSource.manual,
    )
    if investment_type:
        txn.investment_type = investment_type
        txn.investment_subtype = investment_subtype
        txn.security_name = security_name
        txn.quantity = quantity
        txn.price = price
        db.commit()
    return "created"


def seed_investment_baseline(db: Session) -> dict[str, int | list[str]]:
    equity = db.query(Account).filter(Account.slug == "opening_equity").first()
    if not equity:
        return {"error": "missing opening_equity", "created": 0, "updated": 0, "skipped": 0}

    created = updated = skipped = 0
    accounts_seeded: list[str] = []

    for spec in BASELINE_SPECS:
        acc = _find_account(db, spec.name_match)
        if not acc:
            skipped += 1
            continue

        baseline_date = acc.tracking_start_date or BASELINE_DATE
        positions = list(spec.positions)

        if not positions and spec.cash <= 0:
            skipped += 1
            continue

        securities_cost = sum((p.cost for p in positions), Decimal("0"))
        total_inflow = securities_cost + spec.cash

        ext_contrib = f"{BASELINE_PREFIX}{acc.id}:contribution"
        result = _upsert_baseline_txn(
            db,
            external_id=ext_contrib,
            txn_date=baseline_date,
            payee="Opening portfolio contribution",
            amount=total_inflow,
            account_id=acc.id,
            equity_id=equity.id,
        )
        if result == "created":
            created += 1
        else:
            updated += 1

        for pos in positions:
            price = (pos.cost / pos.quantity).quantize(Decimal("0.0001")) if pos.quantity else Decimal("0")
            ext_buy = f"{BASELINE_PREFIX}{acc.id}:buy:{pos.ticker}"
            result = _upsert_baseline_txn(
                db,
                external_id=ext_buy,
                txn_date=baseline_date,
                payee=f"Opening position — {pos.security_name}",
                amount=-pos.cost,
                account_id=acc.id,
                equity_id=equity.id,
                investment_type="buy",
                investment_subtype="buy",
                security_name=pos.ticker,
                quantity=pos.quantity,
                price=price,
            )
            if result == "created":
                created += 1
            else:
                updated += 1

        rebuild_holdings_from_transactions(db, acc.id)
        accounts_seeded.append(acc.name)

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "accounts": accounts_seeded,
    }
