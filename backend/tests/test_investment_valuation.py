from datetime import date
from decimal import Decimal
from unittest.mock import patch

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.account_mark import AccountMark
from app.models.transaction import Transaction
from app.schemas.transaction import EntryLine, TransactionCreate
from app.services.holdings import (
    investment_account_value,
    list_holdings,
    portfolio_value,
    set_holding_position,
)
from app.services.posting import create_transaction
from app.services.register import get_register
from app.services.seed import DEFAULT_TRACKING_START
from app.services.slug import unique_account_slug


def _add_account(db, name, subtype, **kwargs):
    acc = Account(
        name=name,
        slug=unique_account_slug(db, name),
        account_type=AccountType.asset,
        subtype=subtype,
        sync_source=SyncSource.manual,
        tracking_start_date=DEFAULT_TRACKING_START,
        **kwargs,
    )
    db.add(acc)
    db.flush()
    return acc


def test_holding_gain_uses_market_price(db_session):
    acc = _add_account(db_session, "Val Brokerage", AccountSubtype.brokerage)
    set_holding_position(
        db_session,
        acc.id,
        ticker="BST",
        security_name="BST",
        quantity=Decimal("10"),
        cost_basis_total=Decimal("400"),
        market_price=Decimal("50"),
        as_of_date=date(2026, 6, 22),
    )
    db_session.commit()
    holdings = list_holdings(db_session, acc.id)
    assert len(holdings) == 1
    assert holdings[0].market_value == Decimal("500")
    assert holdings[0].gain == Decimal("100")


def test_plaid_balance_overrides_stale_mark(db_session):
    acc = _add_account(db_session, "Plaid Brokerage", AccountSubtype.brokerage)
    from app.models.plaid import PlaidAccount, PlaidItem

    item = PlaidItem(
        item_id="item-plaid-brokerage",
        access_token_encrypted="enc",
        institution_name="Chase",
    )
    db_session.add(item)
    db_session.flush()
    db_session.add(
        PlaidAccount(
            plaid_item_id=item.id,
            plaid_account_id="plaid-brokerage-1",
            account_id=acc.id,
            name=acc.name,
            balance_current=Decimal("12500.42"),
        )
    )
    db_session.add(
        AccountMark(
            account_id=acc.id,
            as_of_date=date(2026, 6, 22),
            market_value=Decimal("58.93"),
            note="stale",
        )
    )
    db_session.commit()

    from app.services.ledger import account_balance

    cash, port = portfolio_value(db_session, acc.id)
    assert port == Decimal("12500.42")
    assert account_balance(db_session, acc.id) == Decimal("12500.42")


def test_portfolio_value_prefers_account_mark(db_session):
    acc = _add_account(db_session, "Mark Brokerage", AccountSubtype.brokerage)
    equity = db_session.query(Account).filter(Account.slug == "opening_equity").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=DEFAULT_TRACKING_START,
            payee="Opening",
            external_id=f"opening-test:{acc.id}",
            entries=[
                EntryLine(account_id=acc.id, amount=Decimal("100")),
                EntryLine(account_id=equity.id, amount=Decimal("-100")),
            ],
        ),
    )
    db_session.add(
        AccountMark(
            account_id=acc.id,
            as_of_date=date(2026, 6, 22),
            market_value=Decimal("50000"),
            note="test",
        )
    )
    db_session.commit()
    cash, port = portfolio_value(db_session, acc.id)
    assert port == Decimal("50000")


def test_register_tracking_cutoff_after_reset_date(db_session):
    acc = _add_account(db_session, "Cutoff Brokerage", AccountSubtype.brokerage)
    equity = db_session.query(Account).filter(Account.slug == "opening_equity").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 5, 1),
            payee="Old trade",
            entries=[
                EntryLine(account_id=acc.id, amount=Decimal("-100")),
                EntryLine(account_id=equity.id, amount=Decimal("100")),
            ],
        ),
    )
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 25),
            payee="New trade",
            entries=[
                EntryLine(account_id=acc.id, amount=Decimal("-50")),
                EntryLine(account_id=equity.id, amount=Decimal("50")),
            ],
        ),
    )
    db_session.commit()
    reg = get_register(db_session, acc.id)
    assert len(reg.rows) == 1
    assert reg.rows[0].payee == "New trade"
    assert reg.tracking_start_date == DEFAULT_TRACKING_START


def test_register_holdings_as_of_date(db_session):
    acc = _add_account(db_session, "AsOf Brokerage", AccountSubtype.brokerage)
    set_holding_position(
        db_session,
        acc.id,
        ticker="TSLA",
        security_name="TSLA",
        quantity=Decimal("1"),
        cost_basis_total=Decimal("200"),
        market_price=Decimal("250"),
        as_of_date=date(2026, 6, 22),
    )
    db_session.commit()
    reg = get_register(db_session, acc.id)
    assert reg.holdings_as_of_date == date(2026, 6, 22)


def test_investment_value_prefers_plaid_total_over_holdings_sum(db_session):
    acc = _add_account(db_session, "Linked Roth", AccountSubtype.retirement)
    from app.models.plaid import PlaidAccount, PlaidItem

    item = PlaidItem(
        item_id="item-roth",
        access_token_encrypted="enc",
        institution_name="Chase",
    )
    db_session.add(item)
    db_session.flush()
    db_session.add(
        PlaidAccount(
            plaid_item_id=item.id,
            plaid_account_id="plaid-roth",
            account_id=acc.id,
            name=acc.name,
            balance_current=Decimal("60788.61"),
        )
    )
    set_holding_position(
        db_session,
        acc.id,
        ticker="LC",
        security_name="LendingClub Corp",
        quantity=Decimal("21"),
        cost_basis_total=Decimal("323.06"),
        market_price=Decimal("18.655"),
        as_of_date=date(2026, 6, 22),
    )
    set_holding_position(
        db_session,
        acc.id,
        ticker="HAPN",
        security_name="Happen Inc.",
        quantity=Decimal("21"),
        cost_basis_total=Decimal("323.06"),
        market_price=Decimal("18.78"),
        as_of_date=date(2026, 7, 9),
    )
    db_session.commit()

    assert investment_account_value(db_session, acc.id) == Decimal("60788.61")


@patch("app.services.market_quotes.fetch_live_quotes")
def test_refresh_live_investment_values_updates_account_total(mock_quotes, db_session, monkeypatch):
    monkeypatch.setenv("LIVE_MARKET_QUOTES_ENABLED", "true")
    from app.config import _load_settings

    _load_settings.cache_clear()
    acc = _add_account(db_session, "Live Roth", AccountSubtype.retirement)
    from app.models.plaid import PlaidAccount, PlaidItem

    item = PlaidItem(
        item_id="item-live",
        access_token_encrypted="enc",
        institution_name="Chase",
    )
    db_session.add(item)
    db_session.flush()
    db_session.add(
        PlaidAccount(
            plaid_item_id=item.id,
            plaid_account_id="plaid-live-roth",
            account_id=acc.id,
            name=acc.name,
            balance_current=Decimal("100"),
        )
    )
    set_holding_position(
        db_session,
        acc.id,
        ticker="TSLA",
        security_name="Tesla Inc",
        quantity=Decimal("2"),
        cost_basis_total=Decimal("700"),
        market_price=Decimal("350"),
        as_of_date=date(2026, 6, 22),
    )
    db_session.commit()
    mock_quotes.return_value = {"TSLA": Decimal("406.55")}

    from app.services.holdings import refresh_live_investment_values

    result = refresh_live_investment_values(db_session)
    assert result["quotes_fetched"] == 1
    assert result["accounts_updated"] == 1
    assert investment_account_value(db_session, acc.id) == Decimal("813.10")
