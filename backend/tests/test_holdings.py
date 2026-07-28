from datetime import date
from decimal import Decimal

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.account_mark import AccountMark
from app.models.holding import Holding
from app.schemas.transaction import EntryLine, TransactionCreate
from app.models.transaction import Transaction
from app.services.holdings import (
    apply_investment_txn,
    cash_ledger_balance,
    list_holdings,
    portfolio_value,
    set_holding_position,
)
from app.services.posting import create_transaction
from app.services.slug import unique_account_slug


def _brokerage(db):
    acc = Account(
        name="Test Brokerage",
        slug=unique_account_slug(db, "Test Brokerage"),
        account_type=AccountType.asset,
        subtype=AccountSubtype.brokerage,
        sync_source=SyncSource.manual,
    )
    db.add(acc)
    db.flush()
    return acc


def test_set_holding_and_market_value(db_session):
    acc = _brokerage(db_session)
    set_holding_position(
        db_session,
        acc.id,
        ticker="BST",
        security_name="BLACKROCK SCIENCE",
        quantity=Decimal("1.07321"),
        cost_basis_total=Decimal("39.68"),
        market_price=Decimal("49.06"),
    )
    db_session.commit()
    holdings = list_holdings(db_session, acc.id)
    assert len(holdings) == 1
    assert holdings[0].ticker == "BST"
    assert holdings[0].market_value > Decimal("50")


def test_apply_buy_increases_holding(db_session):
    acc = _brokerage(db_session)
    equity = db_session.query(Account).filter(Account.slug == "opening_equity").one()
    txn = create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 2, 1),
            payee="Buy BST",
            entries=[
                EntryLine(account_id=acc.id, amount=Decimal("-10")),
                EntryLine(account_id=equity.id, amount=Decimal("10")),
            ],
        ),
    )
    txn.investment_type = "buy"
    txn.investment_subtype = "buy"
    txn.security_name = "BST"
    txn.quantity = Decimal("0.2")
    txn.price = Decimal("50")
    db_session.commit()

    apply_investment_txn(db_session, txn, acc.id)
    db_session.commit()

    holding = (
        db_session.query(Holding)
        .filter(Holding.account_id == acc.id, Holding.ticker == "BST")
        .one()
    )
    assert holding.quantity == Decimal("0.2")
    assert holding.cost_basis_total == Decimal("10")


def test_portfolio_value_uses_priced_holdings(db_session):
    acc = _brokerage(db_session)
    equity = db_session.query(Account).filter(Account.slug == "opening_equity").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 1, 1),
            payee="Cash",
            entries=[
                EntryLine(account_id=acc.id, amount=Decimal("6.10")),
                EntryLine(account_id=equity.id, amount=Decimal("-6.10")),
            ],
        ),
    )
    set_holding_position(
        db_session,
        acc.id,
        ticker="BST",
        security_name="BST",
        quantity=Decimal("1"),
        cost_basis_total=Decimal("40"),
        market_price=Decimal("52"),
    )
    db_session.add(
        AccountMark(account_id=acc.id, as_of_date=date.today(), market_value=Decimal("58.75"))
    )
    db_session.commit()

    cash, portfolio = portfolio_value(db_session, acc.id)
    assert cash == Decimal("6.10")
    assert portfolio == Decimal("58.10")


def test_cash_ledger_balance(db_session):
    acc = _brokerage(db_session)
    equity = db_session.query(Account).filter(Account.slug == "opening_equity").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 1, 5),
            payee="Deposit",
            entries=[
                EntryLine(account_id=acc.id, amount=Decimal("25")),
                EntryLine(account_id=equity.id, amount=Decimal("-25")),
            ],
        ),
    )
    db_session.commit()
    assert cash_ledger_balance(db_session, acc.id) == Decimal("25")
