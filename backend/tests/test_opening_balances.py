from datetime import date
from decimal import Decimal

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.plaid import PlaidAccount, PlaidItem
from app.models.transaction import Transaction
from app.schemas.transaction import EntryLine, TransactionCreate
from app.services.ledger import account_balance
from app.services.opening_balances import (
    compute_opening_entry_amount,
    net_entry_change_since_tracking,
    seed_opening_balances,
)
from app.services.posting import create_transaction
from app.services.seed import DEFAULT_TRACKING_START
from app.services.slug import unique_account_slug


def _add_account(db, name: str, atype: AccountType, subtype: AccountSubtype, **kwargs) -> Account:
    sync = kwargs.pop("sync_source", SyncSource.manual)
    acc = Account(
        name=name,
        slug=unique_account_slug(db, name),
        account_type=atype,
        subtype=subtype,
        sync_source=sync,
        **kwargs,
    )
    db.add(acc)
    db.flush()
    return acc


def _link_plaid(db, acc: Account, balance: Decimal) -> None:
    item = PlaidItem(
        item_id="item-test",
        access_token_encrypted="enc",
        institution_name="Test Bank",
    )
    db.add(item)
    db.flush()
    db.add(
        PlaidAccount(
            plaid_item_id=item.id,
            plaid_account_id=f"plaid-{acc.id}",
            account_id=acc.id,
            name=acc.name,
            balance_current=balance,
        )
    )
    db.commit()


def test_compute_opening_asset_backed_out_from_plaid(db_session):
    checking = _add_account(
        db_session,
        "Opening Checking",
        AccountType.asset,
        AccountSubtype.checking,
        tracking_start_date=DEFAULT_TRACKING_START,
        sync_source=SyncSource.plaid,
    )
    income = db_session.query(Account).filter(Account.slug == "salary_income").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 25),
            payee="Paycheck",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("500")),
                EntryLine(account_id=income.id, amount=Decimal("-500")),
            ],
        ),
    )
    net = net_entry_change_since_tracking(
        db_session, checking.id, DEFAULT_TRACKING_START
    )
    assert net == Decimal("500")
    opening = compute_opening_entry_amount(
        AccountType.asset, Decimal("5002.13"), net
    )
    assert opening == Decimal("4502.13")


def test_seed_opening_balances_matches_plaid_current(db_session):
    checking = _add_account(
        db_session,
        "Plaid Checking",
        AccountType.asset,
        AccountSubtype.checking,
        tracking_start_date=DEFAULT_TRACKING_START,
        sync_source=SyncSource.plaid,
    )
    _link_plaid(db_session, checking, Decimal("5002.13"))
    income = db_session.query(Account).filter(Account.slug == "salary_income").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 25),
            payee="Deposit",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("200")),
                EntryLine(account_id=income.id, amount=Decimal("-200")),
            ],
        ),
    )

    result = seed_opening_balances(db_session)
    assert result["created"] == 1

    bal = account_balance(db_session, checking.id)
    assert bal == Decimal("5002.13")

    opening_txn = (
        db_session.query(Transaction)
        .filter(Transaction.external_id == f"opening:{checking.id}")
        .one()
    )
    opening_entry = next(e for e in opening_txn.entries if e.account_id == checking.id)
    assert opening_entry.amount == Decimal("4802.13")


def test_seed_opening_balances_updates_existing_entry(db_session):
    checking = _add_account(
        db_session,
        "Repair Checking",
        AccountType.asset,
        AccountSubtype.checking,
        tracking_start_date=DEFAULT_TRACKING_START,
        sync_source=SyncSource.plaid,
    )
    equity = db_session.query(Account).filter(Account.slug == "opening_equity").one()
    _link_plaid(db_session, checking, Decimal("5002.13"))

    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=DEFAULT_TRACKING_START,
            payee="Opening balance",
            external_id=f"opening:{checking.id}",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("10214.18")),
                EntryLine(account_id=equity.id, amount=Decimal("-10214.18")),
            ],
        ),
    )

    result = seed_opening_balances(db_session)
    assert result["updated"] == 1
    assert account_balance(db_session, checking.id) == Decimal("5002.13")


def test_seed_opening_balances_liability_credit_card(db_session):
    card = _add_account(
        db_session,
        "Plaid Card",
        AccountType.liability,
        AccountSubtype.credit_card,
        tracking_start_date=DEFAULT_TRACKING_START,
        sync_source=SyncSource.plaid,
    )
    _link_plaid(db_session, card, Decimal("555.64"))
    expense = db_session.query(Account).filter(Account.slug == "uncategorized_expense").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 25),
            payee="Store",
            entries=[
                EntryLine(account_id=expense.id, amount=Decimal("50")),
                EntryLine(account_id=card.id, amount=Decimal("-50")),
            ],
        ),
    )

    seed_opening_balances(db_session)
    bal = account_balance(db_session, card.id)
    assert bal == Decimal("555.64")
