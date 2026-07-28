"""Tests for Plaid sync scheduling and account mark upserts."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.account_mark import AccountMark
from app.models.plaid import PlaidAccount, PlaidItem
from app.services.plaid_sync import _plaid_str, _upsert_account_mark, sync_due
from app.services.slug import unique_account_slug


def test_plaid_str_coerces_enums():
    class FakeEnum:
        value = "depository"

    assert _plaid_str(FakeEnum()) == "depository"
    assert _plaid_str("checking") == "checking"
    assert _plaid_str(None) is None


def test_sync_due_when_never_synced():
    assert sync_due(None, 7) is True


def test_sync_due_within_interval():
    recent = datetime.now(timezone.utc) - timedelta(days=2)
    assert sync_due(recent, 7) is False


def test_sync_due_after_interval():
    old = datetime.now(timezone.utc) - timedelta(days=8)
    assert sync_due(old, 7) is True


def test_upsert_account_mark_updates_existing(db_session):
    acc = Account(
        name="Brokerage",
        slug=unique_account_slug(db_session, "Brokerage"),
        account_type=AccountType.asset,
        subtype=AccountSubtype.brokerage,
        sync_source=SyncSource.manual,
    )
    db_session.add(acc)
    db_session.flush()

    as_of = date(2026, 6, 1)
    _upsert_account_mark(db_session, acc.id, as_of, Decimal("10000"), "first")
    db_session.commit()
    _upsert_account_mark(db_session, acc.id, as_of, Decimal("12000"), "updated")
    db_session.commit()

    marks = db_session.query(AccountMark).filter(AccountMark.account_id == acc.id).all()
    assert len(marks) == 1
    assert marks[0].market_value == Decimal("12000")
    assert marks[0].note == "updated"


def test_sync_all_profiles_without_plaid(monkeypatch):
    from app.services import plaid_scheduler

    monkeypatch.setattr(
        "app.services.plaid_scheduler.get_settings",
        lambda: type("S", (), {"plaid_enabled": False, "plaid_configured": False})(),
    )
    assert plaid_scheduler.sync_all_profiles() == []


def test_plaid_to_dict_from_sdk_model():
    from app.services.plaid_sync import _plaid_to_dict

    class FakeTxn:
        def to_dict(self):
            return {
                "investment_transaction_id": "abc",
                "account_id": "acct1",
                "amount": 10.5,
                "date": "2026-01-15",
                "name": "Buy AAPL",
                "type": "buy",
            }

    d = _plaid_to_dict(FakeTxn())
    assert d["investment_transaction_id"] == "abc"
    assert {**d, "_securities": {}}["name"] == "Buy AAPL"


def test_infer_investment_mapping_metadata(db_session):
    item = PlaidItem(
        item_id="item_test",
        access_token_encrypted="enc",
        institution_name="Chase",
    )
    db_session.add(item)
    db_session.flush()

    pa = PlaidAccount(
        plaid_item_id=item.id,
        plaid_account_id="acct_roth",
        name="Roth IRA",
        plaid_type="investment",
        plaid_subtype="roth",
    )
    db_session.add(pa)
    db_session.commit()

    from app.services.plaid_sync import _infer_ledger_types

    atype, subtype = _infer_ledger_types(pa)
    assert atype == AccountType.asset
    assert subtype == AccountSubtype.retirement
