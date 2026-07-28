"""Tests for card payment deduplication and category rule application."""

import json
from datetime import date
from decimal import Decimal

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.import_staging import ImportStaging, StagingStatus
from app.models.plaid import PlaidAccount, PlaidItem
from app.models.transaction import Transaction, TransactionSource
from app.schemas.transaction import EntryLine, TransactionCreate
from app.services.card_payments import find_card_payment_txn, repair_duplicate_card_payments
from app.services.categorization import create_rule
from app.services.plaid_sync import _post_staged_row
from app.services.posting import create_transaction
from app.services.register import get_register
from app.services.seed import DEFAULT_TRACKING_START
from app.services.slug import unique_account_slug


def _add_account(db, name: str, atype: AccountType, subtype: AccountSubtype, **kwargs) -> Account:
    acc = Account(
        name=name,
        slug=unique_account_slug(db, name),
        account_type=atype,
        subtype=subtype,
        sync_source=kwargs.pop("sync_source", SyncSource.manual),
        **kwargs,
    )
    db.add(acc)
    db.flush()
    return acc


def _setup_chase_plaid(db):
    checking = _add_account(
        db,
        "Checking",
        AccountType.asset,
        AccountSubtype.checking,
        tracking_start_date=DEFAULT_TRACKING_START,
    )
    card = _add_account(
        db,
        "Visa",
        AccountType.liability,
        AccountSubtype.credit_card,
        tracking_start_date=DEFAULT_TRACKING_START,
    )
    item = PlaidItem(item_id="item1", access_token_encrypted="enc", institution_name="Chase")
    db.add(item)
    db.flush()
    checking_pa = PlaidAccount(
        plaid_item_id=item.id,
        plaid_account_id="plaid_checking",
        name="Checking",
        mask="1234",
        account_id=checking.id,
    )
    card_pa = PlaidAccount(
        plaid_item_id=item.id,
        plaid_account_id="plaid_card",
        name="Visa",
        mask="5047",
        plaid_type="credit",
        plaid_subtype="credit card",
        account_id=card.id,
    )
    db.add_all([checking_pa, card_pa])
    db.commit()
    return checking, card, item, checking_pa, card_pa


def test_checking_card_payment_skips_when_card_side_already_posted(db_session):
    checking, card, _item, checking_pa, card_pa = _setup_chase_plaid(db_session)

    card_row = ImportStaging(
        external_id="plaid:card:pay1",
        txn_date=date(2026, 6, 25),
        amount=Decimal("150.47"),
        payee="Payment Thank You - Web",
        raw_json=json.dumps({"amount": -150.47, "name": "Payment Thank You - Web"}),
        plaid_account_id=card_pa.id,
        status=StagingStatus.pending,
    )
    db_session.add(card_row)
    db_session.commit()
    _post_staged_row(db_session, card_row, card, card_pa)

    checking_row = ImportStaging(
        external_id="plaid:checking:pay1",
        txn_date=date(2026, 6, 25),
        amount=Decimal("-150.47"),
        payee="Payment to Chase card ending in 5047 06/18",
        raw_json=json.dumps(
            {
                "amount": 150.47,
                "name": "Payment to Chase card ending in 5047 06/18",
                "personal_finance_category": {"detailed": "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"},
            }
        ),
        plaid_account_id=checking_pa.id,
        status=StagingStatus.pending,
    )
    db_session.add(checking_row)
    db_session.commit()
    _post_staged_row(db_session, checking_row, checking, checking_pa)
    db_session.commit()

    reg = get_register(db_session, checking.id)
    payment_rows = [r for r in reg.rows if abs(float(r.charge or 0) - 150.47) < 0.01]
    assert len(payment_rows) == 1
    assert payment_rows[0].payee == "Payment Thank You - Web"


def test_repair_duplicate_card_payments(db_session):
    checking, card, _item, _checking_pa, card_pa = _setup_chase_plaid(db_session)
    expense = db_session.query(Account).filter(Account.slug == "uncategorized_expense").one()

    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 25),
            payee="Payment Thank You - Web",
            external_id="good:pay1",
            entries=[
                EntryLine(account_id=card.id, amount=Decimal("150.47")),
                EntryLine(account_id=checking.id, amount=Decimal("-150.47")),
            ],
        ),
        source=TransactionSource.plaid,
    )
    duplicate = create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 25),
            payee="Payment to Chase card ending in 5047 06/18",
            external_id="bad:pay1",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("-150.47")),
                EntryLine(account_id=expense.id, amount=Decimal("150.47")),
            ],
        ),
        source=TransactionSource.plaid,
    )
    db_session.add(
        ImportStaging(
            external_id="bad:pay1",
            txn_date=date(2026, 6, 25),
            amount=Decimal("-150.47"),
            payee="Payment to Chase card ending in 5047 06/18",
            raw_json=json.dumps(
                {
                    "amount": 150.47,
                    "name": "Payment to Chase card ending in 5047 06/18",
                    "personal_finance_category": {"detailed": "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"},
                }
            ),
            plaid_account_id=card_pa.id,
            status=StagingStatus.posted,
        )
    )
    db_session.commit()

    result = repair_duplicate_card_payments(db_session)
    assert result["voided"] == 1
    db_session.refresh(duplicate)
    assert duplicate.voided_at is not None

    reg = get_register(db_session, checking.id)
    assert len(reg.rows) == 1


def test_create_rule_applies_to_matching_transactions(db_session):
    checking = _add_account(
        db_session,
        "Rule Checking",
        AccountType.asset,
        AccountSubtype.checking,
        tracking_start_date=DEFAULT_TRACKING_START,
    )
    card = _add_account(
        db_session,
        "Rule Card",
        AccountType.liability,
        AccountSubtype.credit_card,
        tracking_start_date=DEFAULT_TRACKING_START,
    )
    from app.models.category import Category

    cat = db_session.query(Category).filter(Category.slug == "groceries").one()

    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 25),
            payee="Payment Thank You - Web",
            entries=[
                EntryLine(account_id=card.id, amount=Decimal("50")),
                EntryLine(account_id=checking.id, amount=Decimal("-50")),
            ],
        ),
    )
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 10),
            payee="Payment Thank You - Web",
            entries=[
                EntryLine(account_id=card.id, amount=Decimal("25")),
                EntryLine(account_id=checking.id, amount=Decimal("-25")),
            ],
        ),
    )

    rule, applied = create_rule(
        db_session,
        pattern="Payment Thank You - Web",
        category_id=cat.id,
    )
    assert applied == 2
    reg = get_register(db_session, checking.id)
    assert all(r.category_id == cat.id for r in reg.rows)


def test_find_card_payment_txn_with_date_tolerance(db_session):
    checking, card, *_ = _setup_chase_plaid(db_session)
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 4, 5),
            payee="Payment Thank You - Web",
            entries=[
                EntryLine(account_id=card.id, amount=Decimal("1263.17")),
                EntryLine(account_id=checking.id, amount=Decimal("-1263.17")),
            ],
        ),
    )
    from app.services.card_payments import CARD_PAYMENT_DATE_TOLERANCE_DAYS

    found = find_card_payment_txn(
        db_session,
        date(2026, 4, 6),
        Decimal("1263.17"),
        card.id,
        date_tolerance_days=CARD_PAYMENT_DATE_TOLERANCE_DAYS,
    )
    assert found is not None


def test_find_card_payment_txn(db_session):
    checking, card, *_ = _setup_chase_plaid(db_session)
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 1),
            payee="Payment Thank You - Web",
            entries=[
                EntryLine(account_id=card.id, amount=Decimal("100")),
                EntryLine(account_id=checking.id, amount=Decimal("-100")),
            ],
        ),
    )
    found = find_card_payment_txn(db_session, date(2026, 6, 1), Decimal("100"), card.id)
    assert found is not None
    assert found.payee == "Payment Thank You - Web"
