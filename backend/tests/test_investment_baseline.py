from datetime import date
from decimal import Decimal
from unittest.mock import patch

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.transaction import Transaction
from app.services.investment_baseline import (
    BASELINE_DATE,
    BaselineAccountSpec,
    BaselinePosition,
    seed_investment_baseline,
)
from app.services.register import get_register
from app.services.seed import DEFAULT_TRACKING_START
from app.services.slug import unique_account_slug


def _roth(db):
    acc = Account(
        name="Roth IRA",
        slug=unique_account_slug(db, "Roth IRA Test"),
        account_type=AccountType.asset,
        subtype=AccountSubtype.retirement,
        sync_source=SyncSource.plaid,
        tracking_start_date=DEFAULT_TRACKING_START,
    )
    db.add(acc)
    db.flush()
    return acc


def test_seed_baseline_creates_transactions(db_session):
    acc = _roth(db_session)
    specs = (
        BaselineAccountSpec(
            name_match="Roth IRA",
            cash=Decimal("7.80"),
            positions=(
                BaselinePosition(
                    ticker="TSLA",
                    security_name="TESLA INC COMMON STOCK",
                    quantity=Decimal("10"),
                    cost=Decimal("1000"),
                ),
            ),
        ),
    )
    with patch("app.services.investment_baseline.BASELINE_SPECS", specs):
        result = seed_investment_baseline(db_session)
    assert result.get("created", 0) > 0 or result.get("updated", 0) > 0

    contrib = (
        db_session.query(Transaction)
        .filter(Transaction.external_id == f"baseline:{acc.id}:contribution")
        .first()
    )
    assert contrib is not None
    assert contrib.txn_date == (acc.tracking_start_date or BASELINE_DATE)

    buy = (
        db_session.query(Transaction)
        .filter(Transaction.external_id == f"baseline:{acc.id}:buy:TSLA")
        .first()
    )
    assert buy is not None

    reg = get_register(db_session, acc.id)
    assert reg is not None


def test_seed_baseline_noop_when_empty_specs(db_session):
    _roth(db_session)
    with patch("app.services.investment_baseline.BASELINE_SPECS", ()):
        result = seed_investment_baseline(db_session)
    assert result.get("created", 0) == 0
    assert result.get("accounts") == []
