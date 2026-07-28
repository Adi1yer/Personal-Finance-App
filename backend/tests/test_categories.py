from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.category import Category, CategoryType
from app.models.entry import Entry
from app.schemas.transaction import EntryLine, TransactionCreate
from app.services.categories import delete_category, update_category
from app.services.posting import create_transaction
from app.services.seed import PROTECTED_CATEGORY_SLUGS
from app.services.slug import unique_account_slug, unique_category_slug


def test_update_category_name(db_session):
    cat = db_session.query(Category).filter(Category.slug == "groceries").one()
    updated = update_category(db_session, cat.id, name="Food at home")
    assert updated.name == "Food at home"
    assert updated.slug == "groceries"


def test_update_category_type(db_session):
    cat = db_session.query(Category).filter(Category.slug == "groceries").one()
    updated = update_category(db_session, cat.id, category_type=CategoryType.income)
    assert updated.category_type == CategoryType.income


def test_delete_custom_category_clears_entries(db_session):
    custom = Category(
        name="Temp Cat",
        slug=unique_category_slug(db_session, "Temp Cat"),
        category_type=CategoryType.expense,
    )
    db_session.add(custom)
    db_session.flush()

    card = Account(
        name="Card",
        slug=unique_account_slug(db_session, "Card"),
        account_type=AccountType.liability,
        subtype=AccountSubtype.credit_card,
        sync_source=SyncSource.manual,
    )
    db_session.add(card)
    db_session.flush()
    expense = db_session.query(Account).filter(Account.slug == "uncategorized_expense").one()

    txn = create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 1, 1),
            payee="Test",
            entries=[
                EntryLine(account_id=expense.id, amount=Decimal("10"), category_id=custom.id),
                EntryLine(account_id=card.id, amount=Decimal("-10")),
            ],
        ),
    )
    delete_category(db_session, custom.id)
    entry = db_session.get(Entry, txn.entries[0].id)
    assert entry.category_id is None
    assert db_session.get(Category, custom.id) is None


def test_delete_protected_category_rejected(db_session):
    cat = db_session.query(Category).filter(Category.slug == "groceries").one()
    assert cat.slug in PROTECTED_CATEGORY_SLUGS
    with pytest.raises(HTTPException) as exc:
        delete_category(db_session, cat.id)
    assert exc.value.status_code == 400
