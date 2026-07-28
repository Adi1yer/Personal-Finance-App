"""Tests for Plaid data reset."""

from datetime import date
from decimal import Decimal

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.entry import Entry
from app.models.import_staging import ImportStaging, StagingStatus
from app.models.plaid import PlaidAccount, PlaidItem
from app.models.transaction import Transaction, TransactionSource
from app.services.plaid_cleanup import reset_plaid_data
from app.services.slug import unique_account_slug


def test_reset_plaid_data_keeps_accounts(db_session):
    acc = Account(
        name="Checking",
        slug=unique_account_slug(db_session, "Checking"),
        account_type=AccountType.asset,
        subtype=AccountSubtype.checking,
        sync_source=SyncSource.plaid,
    )
    db_session.add(acc)
    db_session.flush()

    item = PlaidItem(item_id="item1", access_token_encrypted="enc")
    db_session.add(item)
    db_session.flush()

    pa = PlaidAccount(
        plaid_item_id=item.id,
        plaid_account_id="pa1",
        name="Plaid Checking",
        account_id=acc.id,
    )
    db_session.add(pa)

    txn = Transaction(
        txn_date=date(2026, 6, 1),
        payee="Sandbox Store",
        source=TransactionSource.plaid,
        external_id="txn1",
    )
    db_session.add(txn)
    db_session.flush()
    db_session.add(
        Entry(
            transaction_id=txn.id,
            account_id=acc.id,
            amount=Decimal("10"),
            entry_date=date(2026, 6, 1),
        )
    )
    db_session.add(
        ImportStaging(
            external_id="txn1",
            txn_date=date(2026, 6, 1),
            amount=Decimal("10"),
            payee="Sandbox Store",
            status=StagingStatus.posted,
        )
    )
    db_session.commit()

    result = reset_plaid_data(db_session)
    assert result["transactions_deleted"] == 1
    assert result["plaid_items_deleted"] == 1

    kept = db_session.get(Account, acc.id)
    assert kept is not None
    assert kept.sync_source == SyncSource.manual
    assert db_session.query(PlaidItem).count() == 0
    assert db_session.query(Transaction).count() == 0
