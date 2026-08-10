from datetime import date
from decimal import Decimal

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.category import Category
from app.schemas.transaction import EntryLine, TransactionCreate
from app.services.posting import create_card_purchase, create_transaction
from app.services.reports import balance_sheet, income_statement, quarter_date_range
from app.services.slug import unique_account_slug


def _add_account(db, name: str, atype: AccountType, subtype: AccountSubtype) -> Account:
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


def test_double_entry_balances(db_session):
    checking = _add_account(db_session, "Test Checking", AccountType.asset, AccountSubtype.checking)
    income = db_session.query(Account).filter(Account.slug == "salary_income").one()
    amt = Decimal("5000.00")
    txn = create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 1, 15),
            payee="Employer",
            entries=[
                EntryLine(account_id=checking.id, amount=amt),
                EntryLine(account_id=income.id, amount=-amt),
            ],
        ),
    )
    total = sum(e.amount for e in txn.entries)
    assert total == 0


def test_accrual_card_purchase(db_session):
    card = _add_account(db_session, "Test Card", AccountType.liability, AccountSubtype.credit_card)
    cat = db_session.query(Category).filter(Category.slug == "groceries").one()
    txn = create_card_purchase(
        db_session,
        date(2026, 2, 1),
        card.id,
        cat.id,
        Decimal("42.50"),
        payee="Market",
    )
    assert len(txn.entries) == 2
    assert sum(e.amount for e in txn.entries) == 0


def test_credit_card_plaid_credit_balance_keeps_negative_sign(db_session):
    """Rewards / overpayment: Plaid reports negative; UI must not abs() it away."""
    from app.models.plaid import PlaidAccount, PlaidItem
    from app.services.ledger import account_balance

    card = _add_account(db_session, "Sapphire", AccountType.liability, AccountSubtype.credit_card)
    item = PlaidItem(item_id="item-cc", access_token_encrypted="enc", institution_name="Chase")
    db_session.add(item)
    db_session.flush()
    db_session.add(
        PlaidAccount(
            plaid_item_id=item.id,
            plaid_account_id="plaid-sapphire",
            account_id=card.id,
            name=card.name,
            balance_current=Decimal("-361.84"),
        )
    )
    db_session.commit()

    assert account_balance(db_session, card.id) == Decimal("-361.84")


def test_voided_entries_excluded_from_balance(db_session):
    from datetime import datetime, timezone

    from app.services.ledger import account_balance

    card = _add_account(db_session, "Void Card", AccountType.liability, AccountSubtype.credit_card)
    cat = db_session.query(Category).filter(Category.slug == "groceries").one()
    expense = db_session.query(Account).filter(Account.slug == "uncategorized_expense").one()
    create_card_purchase(
        db_session,
        date(2026, 2, 1),
        card.id,
        cat.id,
        Decimal("100"),
        payee="Active charge",
    )
    voided = create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 1, 20),
            payee="Voided charge",
            entries=[
                EntryLine(account_id=expense.id, amount=Decimal("9000")),
                EntryLine(account_id=card.id, amount=Decimal("-9000")),
            ],
        ),
    )
    voided.voided_at = datetime.now(timezone.utc)
    db_session.commit()

    assert account_balance(db_session, card.id) == Decimal("100")


def test_quarterly_report_smoke(db_session):
    checking = _add_account(db_session, "Test Checking", AccountType.asset, AccountSubtype.checking)
    income = db_session.query(Account).filter(Account.slug == "salary_income").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 1, 10),
            payee="Paycheck",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("3000")),
                EntryLine(account_id=income.id, amount=Decimal("-3000")),
            ],
        ),
    )
    start, end = quarter_date_range(2026, 1)
    bs = balance_sheet(db_session, end)
    inc = income_statement(db_session, start, end)
    assert bs.total_assets >= Decimal("3000")
    assert inc.total_income == Decimal("3000")
    assert inc.net_income == Decimal("3000")
