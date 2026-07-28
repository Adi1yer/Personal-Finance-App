from datetime import date
from decimal import Decimal

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.account_mark import AccountMark
from app.models.category import Category
from app.schemas.transaction import EntryLine, TransactionCreate
from app.services.categorization import resolve_category_id, create_rule
from app.models.transaction import TransactionSource
from app.services.posting import create_transaction
from app.services.register import get_register
from app.services.reports import reports_readiness
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


def test_categorization_pfc_mapping(db_session):
    raw = '{"personal_finance_category": {"detailed": "FOOD_AND_DRINK_GROCERIES"}}'
    cat_id = resolve_category_id(db_session, payee="Whole Foods", raw_json=raw)
    cat = db_session.get(Category, cat_id)
    assert cat is not None
    assert cat.slug == "groceries"


def test_category_rule_priority(db_session):
    groceries = db_session.query(Category).filter(Category.slug == "groceries").one()
    dining = db_session.query(Category).filter(Category.slug == "dining").one()
    create_rule(db_session, pattern="Whole Foods", category_id=dining.id, priority=20)
    raw = '{"personal_finance_category": {"detailed": "FOOD_AND_DRINK_GROCERIES"}}'
    cat_id = resolve_category_id(db_session, payee="Whole Foods Market", raw_json=raw)
    assert cat_id == dining.id


def test_register_running_balance_with_opening(db_session):
    checking = _add_account(
        db_session,
        "Reg Checking",
        AccountType.asset,
        AccountSubtype.checking,
        tracking_start_date=DEFAULT_TRACKING_START,
    )
    equity = db_session.query(Account).filter(Account.slug == "opening_equity").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=DEFAULT_TRACKING_START,
            payee="Opening balance",
            external_id=f"opening:{checking.id}",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("1000")),
                EntryLine(account_id=equity.id, amount=Decimal("-1000")),
            ],
        ),
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
    reg = get_register(db_session, checking.id)
    assert reg.opening_balance == Decimal("1000")
    assert reg.current_balance == Decimal("1500")
    assert len(reg.rows) == 1
    assert reg.rows[0].running_balance == Decimal("1500")


def test_tracking_cutoff_hides_pre_2026(db_session):
    checking = _add_account(
        db_session,
        "Cutoff Checking",
        AccountType.asset,
        AccountSubtype.checking,
        tracking_start_date=DEFAULT_TRACKING_START,
    )
    income = db_session.query(Account).filter(Account.slug == "salary_income").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2025, 12, 15),
            payee="Old paycheck",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("100")),
                EntryLine(account_id=income.id, amount=Decimal("-100")),
            ],
        ),
    )
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 25),
            payee="New paycheck",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("200")),
                EntryLine(account_id=income.id, amount=Decimal("-200")),
            ],
        ),
    )
    reg = get_register(db_session, checking.id)
    assert len(reg.rows) == 1
    assert reg.rows[0].payee == "New paycheck"


def test_reports_readiness_stale_without_marks(db_session):
    _add_account(
        db_session,
        "401k Test",
        AccountType.asset,
        AccountSubtype.retirement,
        sync_source=SyncSource.manual,
    )
    _add_account(
        db_session,
        "HSA Test",
        AccountType.asset,
        AccountSubtype.hsa,
        sync_source=SyncSource.manual,
    )
    result = reports_readiness(db_session, date(2026, 3, 31))
    assert result["ready"] is False
    assert len(result["stale_accounts"]) == 2


def test_reports_readiness_ok_with_fresh_marks(db_session):
    k401 = _add_account(
        db_session,
        "401k Fresh",
        AccountType.asset,
        AccountSubtype.retirement,
        sync_source=SyncSource.manual,
    )
    hsa = _add_account(
        db_session,
        "HSA Fresh",
        AccountType.asset,
        AccountSubtype.hsa,
        sync_source=SyncSource.manual,
    )
    today = date.today()
    db_session.add(
        AccountMark(account_id=k401.id, as_of_date=today, market_value=Decimal("50000"))
    )
    db_session.add(
        AccountMark(account_id=hsa.id, as_of_date=today, market_value=Decimal("3000"))
    )
    db_session.commit()
    result = reports_readiness(db_session, today)
    assert result["ready"] is True


def test_reports_readiness_fresh_mark_with_future_quarter_end(db_session):
    """Freshness is measured from today, not the report as-of date."""
    k401 = _add_account(
        db_session,
        "401k Q2",
        AccountType.asset,
        AccountSubtype.retirement,
        sync_source=SyncSource.manual,
    )
    today = date.today()
    db_session.add(
        AccountMark(account_id=k401.id, as_of_date=today, market_value=Decimal("50000"))
    )
    db_session.commit()

    q2_end = date(today.year, 6, 30)
    if today > q2_end:
        q2_end = date(today.year, 12, 31)

    result = reports_readiness(db_session, q2_end)
    assert result["ready"] is True


def test_investment_balance_uses_mark_only(db_session):
    brokerage = _add_account(
        db_session,
        "Plaid Brokerage",
        AccountType.asset,
        AccountSubtype.brokerage,
        sync_source=SyncSource.plaid,
    )
    income = db_session.query(Account).filter(Account.slug == "salary_income").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 1, 10),
            payee="Contribution",
            entries=[
                EntryLine(account_id=brokerage.id, amount=Decimal("100")),
                EntryLine(account_id=income.id, amount=Decimal("-100")),
            ],
        ),
    )
    db_session.add(
        AccountMark(
            account_id=brokerage.id,
            as_of_date=date.today(),
            market_value=Decimal("58.75"),
        )
    )
    db_session.commit()

    from app.services.ledger import account_balance

    assert account_balance(db_session, brokerage.id) == Decimal("58.75")


def test_plaid_external_id_dedup(db_session):
    checking = _add_account(
        db_session,
        "Dedup Checking",
        AccountType.asset,
        AccountSubtype.checking,
    )
    income = db_session.query(Account).filter(Account.slug == "salary_income").one()
    body = TransactionCreate(
        txn_date=date(2026, 6, 25),
        payee="Plaid Txn",
        external_id="plaid-txn-123",
        entries=[
            EntryLine(account_id=checking.id, amount=Decimal("-10")),
            EntryLine(account_id=income.id, amount=Decimal("10")),
        ],
    )
    t1 = create_transaction(db_session, body, source=TransactionSource.plaid)
    t2 = create_transaction(db_session, body, source=TransactionSource.plaid)
    assert t1.id == t2.id


def test_create_transaction_reimports_after_voided_external_id(db_session):
    from datetime import datetime, timezone

    from app.services.posting import create_transaction

    checking = _add_account(
        db_session,
        "Void Reimport Checking",
        AccountType.asset,
        AccountSubtype.checking,
    )
    income = db_session.query(Account).filter(Account.slug == "salary_income").one()
    body = TransactionCreate(
        txn_date=date(2026, 6, 24),
        payee="Quality Inn Downtown Salt",
        external_id="j4XpXndgDaFp3O1rNn09uQ1aekOajYTvqZk9Q",
        entries=[
            EntryLine(account_id=checking.id, amount=Decimal("-120")),
            EntryLine(account_id=income.id, amount=Decimal("120")),
        ],
    )
    original = create_transaction(db_session, body, source=TransactionSource.plaid)
    original.voided_at = datetime.now(timezone.utc)
    db_session.commit()

    reimported = create_transaction(db_session, body, source=TransactionSource.plaid)
    db_session.refresh(original)

    assert reimported.id != original.id
    assert reimported.external_id == body.external_id
    assert original.external_id is None
    assert reimported.voided_at is None


def test_register_pending_count_uncleared(db_session):
    checking = _add_account(
        db_session,
        "Pending Checking",
        AccountType.asset,
        AccountSubtype.checking,
        tracking_start_date=DEFAULT_TRACKING_START,
    )
    income = db_session.query(Account).filter(Account.slug == "salary_income").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 25),
            payee="Store",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("-20")),
                EntryLine(account_id=income.id, amount=Decimal("20")),
            ],
        ),
    )
    db_session.commit()

    from app.services.overview import build_overview
    from app.services.register import account_register_pending_count

    assert account_register_pending_count(db_session, checking.id) == 1
    ov = build_overview(db_session)
    cash = next(g for g in ov.groups if g.key == "cash")
    line = next(a for a in cash.accounts if a.name == "Pending Checking")
    assert line.register_pending_count == 1


def test_register_pending_count_caught_up(db_session):
    checking = _add_account(
        db_session,
        "Caught Up Checking",
        AccountType.asset,
        AccountSubtype.checking,
        tracking_start_date=DEFAULT_TRACKING_START,
    )
    db_session.commit()

    from app.services.register import account_register_pending_count

    assert account_register_pending_count(db_session, checking.id) == 0
