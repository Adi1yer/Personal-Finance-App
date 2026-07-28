"""Tests for credit card posting and cross-post repair."""

import json
from datetime import date
from decimal import Decimal

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.entry import Entry
from app.models.import_staging import ImportStaging, StagingStatus
from app.models.plaid import PlaidAccount, PlaidItem
from app.models.transaction import Transaction, TransactionSource
from app.schemas.register import EntryPatch
from app.schemas.transaction import EntryLine, TransactionCreate
from app.services.plaid_sync import _post_staged_row
from app.services.posting import create_transaction
from app.services.posting_repair import repair_card_cross_posted_transactions
from app.services.register import get_register
from app.services.seed import DEFAULT_TRACKING_START
from app.services.slug import unique_account_slug
from app.api.v1.entries import patch_entry


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


def _setup_card_plaid(db):
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
    item = PlaidItem(item_id="item1", access_token_encrypted="enc", institution_name="Bank")
    db.add(item)
    db.flush()
    plaid_acct = PlaidAccount(
        plaid_item_id=item.id,
        plaid_account_id="plaid_card",
        name="Visa",
        plaid_type="credit",
        plaid_subtype="credit card",
        account_id=card.id,
    )
    db.add(plaid_acct)
    db.commit()
    return checking, card, item, plaid_acct


def test_credit_card_purchase_does_not_hit_checking(db_session):
    checking, card, _item, plaid_acct = _setup_card_plaid(db_session)
    row = ImportStaging(
        external_id="plaid:txn:123",
        txn_date=date(2026, 6, 25),
        amount=Decimal("-45.67"),
        payee="Coffee Shop",
        raw_json=json.dumps({"amount": -45.67, "name": "Coffee Shop"}),
        plaid_account_id=plaid_acct.id,
        status=StagingStatus.pending,
    )
    db_session.add(row)
    db_session.commit()

    _post_staged_row(db_session, row, card, plaid_acct)
    db_session.commit()

    checking_reg = get_register(db_session, checking.id)
    card_reg = get_register(db_session, card.id)
    assert len(checking_reg.rows) == 0
    assert len(card_reg.rows) == 1
    assert card_reg.rows[0].payee == "Coffee Shop"


def test_card_payment_still_posts_to_checking(db_session):
    checking, card, _item, plaid_acct = _setup_card_plaid(db_session)
    row = ImportStaging(
        external_id="plaid:txn:pay1",
        txn_date=date(2026, 6, 25),
        amount=Decimal("200.00"),
        payee="Payment Thank You - Web",
        raw_json=json.dumps(
            {
                "amount": -200.0,
                "name": "Payment Thank You - Web",
                "personal_finance_category": {"detailed": "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"},
            }
        ),
        plaid_account_id=plaid_acct.id,
        status=StagingStatus.pending,
    )
    db_session.add(row)
    db_session.commit()

    _post_staged_row(db_session, row, card, plaid_acct)
    db_session.commit()

    checking_reg = get_register(db_session, checking.id)
    card_reg = get_register(db_session, card.id)
    assert len(checking_reg.rows) == 1
    assert len(card_reg.rows) == 1


def test_repair_voids_cross_posted_card_purchases(db_session):
    checking, card, item, plaid_acct = _setup_card_plaid(db_session)
    expense = db_session.query(Account).filter(Account.slug == "uncategorized_expense").one()

    bad = create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 25),
            payee="Bad Cross Post",
            external_id="plaid:txn:bad1",
            entries=[
                EntryLine(account_id=card.id, amount=Decimal("-30")),
                EntryLine(account_id=checking.id, amount=Decimal("30")),
            ],
        ),
        source=TransactionSource.plaid,
    )
    staging = ImportStaging(
        external_id="plaid:txn:bad1",
        txn_date=date(2026, 6, 25),
        amount=Decimal("-30"),
        payee="Bad Cross Post",
        raw_json=json.dumps({"amount": -30, "name": "Bad Cross Post"}),
        plaid_account_id=plaid_acct.id,
        status=StagingStatus.posted,
    )
    db_session.add(staging)
    db_session.commit()

    result = repair_card_cross_posted_transactions(db_session)
    assert result["voided"] == 1
    assert result["requeued"] == 1
    assert result["reposted"] == 1

    db_session.refresh(bad)
    assert bad.voided_at is not None

    checking_reg = get_register(db_session, checking.id)
    card_reg = get_register(db_session, card.id)
    assert len(checking_reg.rows) == 0
    assert len(card_reg.rows) == 1

    txn = (
        db_session.query(Transaction)
        .filter(Transaction.voided_at.is_(None), Transaction.payee == "Bad Cross Post")
        .one()
    )
    entry_accounts = {db_session.get(Account, e.account_id).slug for e in txn.entries}
    assert "uncategorized_expense" in entry_accounts


def test_repair_does_not_requeue_when_semantic_duplicate_exists(db_session):
    checking, card, item, plaid_acct = _setup_card_plaid(db_session)
    expense = db_session.query(Account).filter(Account.slug == "uncategorized_expense").one()

    good = create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 25),
            payee="Bad Cross Post",
            external_id="plaid:txn:good1",
            entries=[
                EntryLine(account_id=card.id, amount=Decimal("-30")),
                EntryLine(account_id=expense.id, amount=Decimal("30")),
            ],
        ),
        source=TransactionSource.plaid,
    )
    bad = create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 25),
            payee="Bad Cross Post",
            external_id="plaid:txn:bad1",
            entries=[
                EntryLine(account_id=card.id, amount=Decimal("-30")),
                EntryLine(account_id=checking.id, amount=Decimal("30")),
            ],
        ),
        source=TransactionSource.plaid,
    )
    staging = ImportStaging(
        external_id="plaid:txn:bad1",
        txn_date=date(2026, 6, 25),
        amount=Decimal("-30"),
        payee="Bad Cross Post",
        raw_json=json.dumps({"amount": -30, "name": "Bad Cross Post"}),
        plaid_account_id=plaid_acct.id,
        status=StagingStatus.posted,
    )
    db_session.add(staging)
    db_session.commit()

    result = repair_card_cross_posted_transactions(db_session)
    assert result["voided"] == 1
    assert result["requeued"] == 0
    assert result["reposted"] == 0

    db_session.refresh(bad)
    db_session.refresh(good)
    assert bad.voided_at is not None
    assert good.voided_at is None

    card_reg = get_register(db_session, card.id)
    assert len(card_reg.rows) == 1


def test_is_card_payment_does_not_treat_purchases_as_payments(db_session):
    from app.services.categorization import is_card_payment

    raw = {"amount": 45.67, "name": "Coffee Shop"}
    assert is_card_payment(raw, 45.67, payee="Coffee Shop") is False


def test_parse_plaid_raw_python_repr(db_session):
    from app.services.categorization import parse_plaid_raw

    raw_json = json.dumps(
        "{'amount': -41.45, 'name': 'Costco', "
        "'authorized_date': datetime.date(2026, 5, 14)}"
    )
    parsed = parse_plaid_raw(raw_json)
    assert parsed["amount"] == -41.45
    assert parsed["name"] == "Costco"


def test_patch_entry_clears_category(db_session):
    checking = _add_account(
        db_session,
        "Patch Checking",
        AccountType.asset,
        AccountSubtype.checking,
        tracking_start_date=DEFAULT_TRACKING_START,
    )
    expense = db_session.query(Account).filter(Account.slug == "uncategorized_expense").one()
    from app.models.category import Category

    cat = db_session.query(Category).filter(Category.slug == "groceries").one()
    txn = create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 3, 1),
            payee="Store",
            entries=[
                EntryLine(account_id=expense.id, amount=Decimal("20"), category_id=cat.id),
                EntryLine(account_id=checking.id, amount=Decimal("-20")),
            ],
        ),
    )
    checking_entry = next(e for e in txn.entries if e.account_id == checking.id)
    patch_entry(checking_entry.id, EntryPatch(category_id=None), db_session)

    for entry in txn.entries:
        db_session.refresh(entry)
        assert entry.category_id is None


def test_patch_entry_category_on_card_payment(db_session):
    checking = _add_account(
        db_session,
        "Pay Checking",
        AccountType.asset,
        AccountSubtype.checking,
        tracking_start_date=DEFAULT_TRACKING_START,
    )
    card = _add_account(
        db_session,
        "Pay Card",
        AccountType.liability,
        AccountSubtype.credit_card,
        tracking_start_date=DEFAULT_TRACKING_START,
    )
    from app.models.category import Category

    cat = db_session.query(Category).filter(Category.slug == "groceries").one()
    txn = create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 25),
            payee="Payment Thank You - Web",
            entries=[
                EntryLine(account_id=card.id, amount=Decimal("150.47")),
                EntryLine(account_id=checking.id, amount=Decimal("-150.47")),
            ],
        ),
        source=TransactionSource.plaid,
    )
    checking_entry = next(e for e in txn.entries if e.account_id == checking.id)
    patch_entry(checking_entry.id, EntryPatch(category_id=cat.id), db_session)

    reg = get_register(db_session, checking.id)
    assert len(reg.rows) == 1
    assert reg.rows[0].category_id == cat.id
    assert reg.rows[0].category_name == cat.name
