from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import Account, AccountSubtype, AccountType
from app.models.entry import Entry
from app.models.transaction import Transaction
from app.services.holdings import investment_account_value, plaid_live_balance

_INVESTMENT_SUBTYPES = frozenset({"brokerage", "retirement", "hsa"})
_PLAID_BALANCE_SUBTYPES = frozenset({AccountSubtype.checking, AccountSubtype.credit_card})


def _balance_sign(account_type: AccountType) -> int:
    """Normal balance: assets/expenses positive with debits; liabilities/income/equity opposite."""
    if account_type in (AccountType.asset, AccountType.expense):
        return 1
    return -1


def account_balance(db: Session, account_id: int, as_of: date | None = None) -> Decimal:
    account = db.get(Account, account_id)
    if not account:
        raise ValueError(f"Account {account_id} not found")

    q = (
        select(func.coalesce(func.sum(Entry.amount), 0))
        .join(Transaction, Entry.transaction_id == Transaction.id)
        .where(
            Entry.account_id == account_id,
            Transaction.voided_at.is_(None),
        )
    )
    if as_of:
        q = q.where(Entry.entry_date <= as_of)
    raw = db.scalar(q) or Decimal("0")
    signed = Decimal(str(raw)) * _balance_sign(account.account_type)

    if account.subtype.value in _INVESTMENT_SUBTYPES:
        return investment_account_value(db, account_id, as_of)

    if (not as_of or as_of >= date.today()) and account.subtype in _PLAID_BALANCE_SUBTYPES:
        plaid_bal = plaid_live_balance(db, account_id)
        if plaid_bal is not None:
            # Checking: always show as a positive asset balance.
            # Credit cards: keep Plaid's sign — positive = amount owed,
            # negative = credit balance (rewards / overpayment).
            if account.subtype == AccountSubtype.credit_card:
                return plaid_bal
            return abs(plaid_bal)

    return signed


def all_account_balances(db: Session, as_of: date | None = None) -> dict[int, Decimal]:
    accounts = db.scalars(select(Account).where(Account.is_active.is_(True))).all()
    return {a.id: account_balance(db, a.id, as_of) for a in accounts}
