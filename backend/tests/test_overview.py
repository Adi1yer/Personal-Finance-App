"""Tests for overview grouping and monthly metrics."""

from datetime import date, datetime, timezone
from decimal import Decimal

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.account_mark import AccountMark
from app.services.overview import build_overview, _group_key
from app.services.reports import monthly_metrics, month_date_range
from app.services.slug import unique_account_slug


def _add(db, name: str, atype: AccountType, subtype: AccountSubtype) -> Account:
    acc = Account(
        name=name,
        slug=unique_account_slug(db, name),
        account_type=atype,
        subtype=subtype,
        sync_source=SyncSource.manual,
    )
    db.add(acc)
    db.flush()
    return acc


def test_group_key_mapping():
    acc = Account(
        name="x",
        slug="x",
        account_type=AccountType.asset,
        subtype=AccountSubtype.checking,
        sync_source=SyncSource.manual,
    )
    assert _group_key(acc) == "cash"


def test_overview_groups_accounts(db_session):
    _add(db_session, "Checking", AccountType.asset, AccountSubtype.checking)
    _add(db_session, "401k", AccountType.asset, AccountSubtype.retirement)
    _add(db_session, "Card", AccountType.liability, AccountSubtype.credit_card)
    db_session.commit()

    ov = build_overview(db_session)
    keys = {g.key for g in ov.groups}
    assert "cash" in keys
    assert "retirement" in keys
    assert "credit_cards" in keys
    assert ov.net_worth == ov.total_assets - ov.total_liabilities


def test_month_date_range():
    start, end = month_date_range(2026, 2)
    assert start == date(2026, 2, 1)
    assert end == date(2026, 2, 28)


def test_monthly_metrics_smoke(db_session):
    m = monthly_metrics(db_session, 2026, 1)
    assert m.year == 2026
    assert m.month == 1
    assert m.total_income >= Decimal("0")


def test_overview_shows_mark_saved_time_not_value_date(db_session):
    k401 = _add(db_session, "401k Time", AccountType.asset, AccountSubtype.retirement)
    old_value_date = date(2026, 1, 1)
    mark = AccountMark(
        account_id=k401.id,
        as_of_date=old_value_date,
        market_value=Decimal("10000"),
    )
    db_session.add(mark)
    db_session.flush()
    mark.updated_at = datetime.now(timezone.utc)
    db_session.commit()

    ov = build_overview(db_session)
    retirement = next(g for g in ov.groups if g.key == "retirement")
    line = next(a for a in retirement.accounts if a.name == "401k Time")
    assert line.last_updated_label in ("Just now", "1m ago", "2m ago", "3m ago", "4m ago", "5m ago")
