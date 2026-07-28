"""Record manual retirement / HSA / brokerage contributions for annual goals."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from app.models.account import Account, AccountSubtype
from app.models.category import Category
from app.models.transaction import Transaction, TransactionSource
from app.schemas.transaction import EntryLine, TransactionCreate
from app.services.investment_baseline import BASELINE_PREFIX
from app.services.investment_contribution_detect import looks_like_external_contribution
from app.services.posting import PostingError, _get_expense_account, create_transaction

_ALLOWED = frozenset(
    {
        AccountSubtype.brokerage,
        AccountSubtype.retirement,
        AccountSubtype.hsa,
    }
)


def ytd_contributions_for_account(db: Session, account_id: int, year: int | None = None) -> Decimal:
    """Sum contribution-like credits on one investment account for the calendar year."""
    year = year or date.today().year
    start = date(year, 1, 1)
    end = date.today()
    total = Decimal("0")
    txns = (
        db.query(Transaction)
        .options(joinedload(Transaction.entries))
        .filter(
            Transaction.voided_at.is_(None),
            Transaction.txn_date >= start,
            Transaction.txn_date <= end,
        )
        .all()
    )
    for txn in txns:
        if txn.external_id and str(txn.external_id).startswith(BASELINE_PREFIX):
            continue
        invest_entries = [e for e in txn.entries if e.account_id == account_id]
        if not invest_entries:
            continue
        other_accounts = {e.account_id for e in txn.entries if e.account_id != account_id}
        is_transfer_in = bool(txn.is_transfer) and any(
            Decimal(str(e.amount)) > 0 for e in invest_entries
        ) and bool(other_accounts)

        for entry in invest_entries:
            amt = Decimal(str(entry.amount))
            if looks_like_external_contribution(
                payee=txn.payee or "",
                memo=txn.memo,
                investment_subtype=txn.investment_subtype,
                amount=amt,
            ):
                total += abs(amt)
                continue
            if is_transfer_in and amt > 0:
                total += amt
    return total.quantize(Decimal("0.01"))


def record_investment_contribution(
    db: Session,
    *,
    account_id: int,
    amount: Decimal,
    txn_date: date,
    memo: str | None = None,
) -> dict:
    """Post new money into an investment account (counts toward investing goal)."""
    acc = db.get(Account, account_id)
    if not acc or not acc.is_active:
        raise PostingError("Account not found")
    if acc.subtype not in _ALLOWED:
        raise PostingError("Contributions can only be recorded on brokerage, retirement, or HSA accounts")

    amt = Decimal(str(amount)).quantize(Decimal("0.01"))
    if amt <= 0:
        raise PostingError("Contribution amount must be positive")

    cat = db.query(Category).filter(Category.slug == "investment_contribution").first()
    expense = _get_expense_account(db)
    txn = create_transaction(
        db,
        TransactionCreate(
            txn_date=txn_date,
            payee=f"{acc.name} contribution",
            memo=memo or "Total contributions",
            entries=[
                EntryLine(account_id=acc.id, amount=amt, category_id=cat.id if cat else None),
                EntryLine(
                    account_id=expense.id,
                    amount=-amt,
                    category_id=cat.id if cat else None,
                ),
            ],
        ),
        source=TransactionSource.manual,
    )
    txn.investment_type = "cash"
    txn.investment_subtype = "contribution"
    db.commit()
    db.refresh(txn)
    return {
        "transaction_id": txn.id,
        "account_id": acc.id,
        "amount": str(amt),
        "txn_date": txn_date.isoformat(),
    }


def set_ytd_total_contributions(
    db: Session,
    *,
    account_id: int,
    total: Decimal,
    as_of: date,
    memo: str | None = None,
) -> dict:
    """Treat `total` as year-to-date contributions; post only the missing amount."""
    target = Decimal(str(total)).quantize(Decimal("0.01"))
    if target < 0:
        raise PostingError("Total contributions cannot be negative")

    current = ytd_contributions_for_account(db, account_id, as_of.year)
    delta = (target - current).quantize(Decimal("0.01"))
    if delta <= 0:
        return {
            "account_id": account_id,
            "ytd_total": str(current),
            "added": "0.00",
            "transaction_id": None,
        }

    posted = record_investment_contribution(
        db,
        account_id=account_id,
        amount=delta,
        txn_date=as_of,
        memo=memo or f"Total contributions set to {target}",
    )
    return {
        "account_id": account_id,
        "ytd_total": str(target),
        "added": str(delta),
        "transaction_id": posted["transaction_id"],
    }
