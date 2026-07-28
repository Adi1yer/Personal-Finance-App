"""Tests for annual investing goal contribution detection."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.transaction import Transaction
from app.schemas.transaction import EntryLine, TransactionCreate
from app.services.annual_goals import (
    _ytd_invested,
    _ytd_invested_breakdown,
    get_annual_goals_progress,
)
from app.services.investment_contributions import (
    record_investment_contribution,
    set_ytd_total_contributions,
    ytd_contributions_for_account,
)
from app.services.posting import create_transaction, create_transfer
from app.services.profile_settings import set_setting


def _invest_account(db, name: str, subtype: AccountSubtype) -> Account:
    acc = Account(
        name=name,
        slug=name.lower().replace(" ", "_").replace("(", "").replace(")", ""),
        account_type=AccountType.asset,
        subtype=subtype,
        sync_source=SyncSource.manual,
        is_active=True,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def _expense(db) -> Account:
    return db.query(Account).filter(Account.slug == "uncategorized_expense").one()


def test_ytd_invested_counts_chase_deposit_sweep_as_contribution(db_session):
    """Plaid maps Chase BANKLINK Roth ACH to a deposit-sweep buy — count it."""
    roth = _invest_account(db_session, "Roth IRA Sweep", AccountSubtype.retirement)
    expense = _expense(db_session)
    today = date.today()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=today,
            payee="CHASE IRA DEPOSIT SWEEP JPMORGAN CHASE BANK NA INTRA-DAY DEPOSIT",
            entries=[
                EntryLine(account_id=roth.id, amount=Decimal("-7500")),
                EntryLine(account_id=expense.id, amount=Decimal("7500")),
            ],
        ),
    )
    txn = db_session.query(Transaction).order_by(Transaction.id.desc()).first()
    txn.investment_type = "buy"
    txn.investment_subtype = "buy"
    db_session.commit()

    assert _ytd_invested(db_session, today.year) == Decimal("7500")


def test_ytd_invested_ignores_tiny_sweep_parking(db_session):
    roth = _invest_account(db_session, "Roth Tiny", AccountSubtype.retirement)
    expense = _expense(db_session)
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date.today(),
            payee="CHASE IRA DEPOSIT SWEEP JPMORGAN CHASE BANK NA INTRA-DAY DEPOSIT",
            entries=[
                EntryLine(account_id=roth.id, amount=Decimal("-7.79")),
                EntryLine(account_id=expense.id, amount=Decimal("7.79")),
            ],
        ),
    )
    txn = db_session.query(Transaction).order_by(Transaction.id.desc()).first()
    txn.investment_subtype = "buy"
    db_session.commit()
    assert _ytd_invested(db_session, date.today().year) == Decimal("0")


def test_ytd_invested_counts_manual_401k_and_hsa_contributions(db_session):
    k401 = _invest_account(db_session, "401k", AccountSubtype.retirement)
    hsa = _invest_account(db_session, "HSA", AccountSubtype.hsa)
    today = date.today()

    record_investment_contribution(
        db_session, account_id=k401.id, amount=Decimal("2000"), txn_date=today
    )
    record_investment_contribution(
        db_session, account_id=hsa.id, amount=Decimal("500"), txn_date=today
    )

    total, breakdown = _ytd_invested_breakdown(db_session, today.year)
    assert total == Decimal("2500.00")
    by_name = {row["name"]: Decimal(row["ytd_contributions"]) for row in breakdown}
    assert by_name["401k"] == Decimal("2000.00")
    assert by_name["HSA"] == Decimal("500.00")


def test_ytd_invested_counts_transfer_into_retirement(db_session):
    checking = Account(
        name="Checking",
        slug="checking_test_goals",
        account_type=AccountType.asset,
        subtype=AccountSubtype.checking,
        sync_source=SyncSource.manual,
        is_active=True,
    )
    db_session.add(checking)
    db_session.commit()
    db_session.refresh(checking)

    roth = _invest_account(db_session, "Roth", AccountSubtype.retirement)
    create_transfer(
        db_session,
        date.today(),
        from_account_id=checking.id,
        to_account_id=roth.id,
        amount=Decimal("1000"),
        memo="Roth contribution",
    )
    assert _ytd_invested(db_session, date.today().year) == Decimal("1000")


def test_goals_progress_includes_by_account(db_session):
    set_setting(db_session, "annual_income_override", 120000)
    set_setting(db_session, "investing_pct_of_income", 20)
    k401 = _invest_account(db_session, "Empower", AccountSubtype.retirement)
    record_investment_contribution(
        db_session,
        account_id=k401.id,
        amount=Decimal("3000"),
        txn_date=date.today(),
    )
    progress = get_annual_goals_progress(db_session)
    assert progress["investing"]["ytd_actual"] == "3000.00"
    assert any(r["name"] == "Empower" for r in progress["investing"]["by_account"])


def test_set_ytd_total_contributions_only_adds_delta(db_session):
    k401 = _invest_account(db_session, "401k Total", AccountSubtype.retirement)
    today = date.today()
    set_ytd_total_contributions(
        db_session, account_id=k401.id, total=Decimal("2000"), as_of=today
    )
    assert ytd_contributions_for_account(db_session, k401.id) == Decimal("2000.00")

    # Entering the same total again should not double-count.
    set_ytd_total_contributions(
        db_session, account_id=k401.id, total=Decimal("2000"), as_of=today
    )
    assert ytd_contributions_for_account(db_session, k401.id) == Decimal("2000.00")

    set_ytd_total_contributions(
        db_session, account_id=k401.id, total=Decimal("2500"), as_of=today
    )
    assert ytd_contributions_for_account(db_session, k401.id) == Decimal("2500.00")
