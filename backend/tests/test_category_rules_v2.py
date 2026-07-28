from datetime import date
from decimal import Decimal

from app.models.account import Account, AccountSubtype, AccountType
from app.models.category import Category
from app.models.category_rule import CategoryRule
from app.models.transaction import Transaction
from app.schemas.transaction import EntryLine, TransactionCreate
from app.services.categorization import (
    create_rule,
    normalize_rule_patterns,
    resolve_category_id,
)
from app.services.category_assignment import apply_category_rule_to_matching
from app.services.posting import create_transaction
from app.services.register import get_register
from app.services.slug import unique_account_slug


def _add_account(db, name: str, atype: AccountType, subtype: AccountSubtype, **kwargs) -> Account:
    sync = kwargs.pop("sync_source", None)
    acc = Account(
        name=name,
        slug=unique_account_slug(db, name),
        account_type=atype,
        subtype=subtype,
        **kwargs,
    )
    if sync is not None:
        from app.models.account import SyncSource

        acc.sync_source = sync
    db.add(acc)
    db.flush()
    return acc


def test_zelle_rules_match_without_id(db_session):
    dining = db_session.query(Category).filter(Category.slug == "dining").one()
    create_rule(
        db_session,
        pattern="Zelle payment to RADHIKA PATWARDHAN",
        category_id=dining.id,
        amount_direction="outflow",
        apply_to_existing=False,
    )
    cat_id = resolve_category_id(
        db_session,
        payee="Zelle payment to RADHIKA PATWARDHAN JPM99ckej76s",
        amount=Decimal("-50"),
    )
    assert cat_id == dining.id


def test_ambiguous_same_direction_rules_do_not_autofill(db_session):
    groceries = db_session.query(Category).filter(Category.slug == "groceries").one()
    dining = db_session.query(Category).filter(Category.slug == "dining").one()
    create_rule(
        db_session,
        pattern="Venmo",
        category_id=groceries.id,
        amount_direction="outflow",
        apply_to_existing=False,
    )
    create_rule(
        db_session,
        pattern="Venmo",
        category_id=dining.id,
        amount_direction="outflow",
        apply_to_existing=False,
    )
    cat_id = resolve_category_id(
        db_session,
        payee="Venmo Payment 12345",
        amount=Decimal("-25"),
    )
    uncategorized = db_session.query(Category).filter(Category.slug == "uncategorized").one()
    assert cat_id == uncategorized.id


def test_direction_filters_venmo_rules(db_session):
    groceries = db_session.query(Category).filter(Category.slug == "groceries").one()
    salary = db_session.query(Category).filter(Category.slug == "salary").one()
    create_rule(
        db_session,
        pattern="Venmo",
        category_id=groceries.id,
        amount_direction="outflow",
        apply_to_existing=False,
    )
    create_rule(
        db_session,
        pattern="Venmo",
        category_id=salary.id,
        amount_direction="inflow",
        apply_to_existing=False,
    )
    out_id = resolve_category_id(
        db_session,
        payee="Venmo Payment 12345",
        amount=Decimal("-25"),
    )
    in_id = resolve_category_id(
        db_session,
        payee="Venmo Payment 12345",
        amount=Decimal("100"),
    )
    assert out_id == groceries.id
    assert in_id == salary.id


def test_safe_retroactive_apply_skips_ambiguous(db_session):
    checking = _add_account(
        db_session,
        "Rule Checking",
        AccountType.asset,
        AccountSubtype.checking,
    )
    groceries = db_session.query(Category).filter(Category.slug == "groceries").one()
    dining = db_session.query(Category).filter(Category.slug == "dining").one()
    expense_acct = db_session.query(Account).filter(Account.slug == "uncategorized_expense").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 2, 1),
            payee="Venmo Payment ABC",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("-20")),
                EntryLine(account_id=expense_acct.id, amount=Decimal("20"), category_id=groceries.id),
            ],
        ),
    )
    create_rule(
        db_session,
        pattern="Venmo",
        category_id=groceries.id,
        amount_direction="outflow",
        apply_to_existing=False,
    )
    create_rule(
        db_session,
        pattern="Venmo",
        category_id=dining.id,
        amount_direction="outflow",
        apply_to_existing=False,
    )
    new_rule, _ = create_rule(
        db_session,
        pattern="Venmo",
        category_id=dining.id,
        amount_direction="outflow",
    )
    applied = apply_category_rule_to_matching(db_session, new_rule)
    assert applied == 0
    txn = db_session.query(Transaction).filter_by(payee="Venmo Payment ABC").one()
    cat_entry = next(e for e in txn.entries if e.category_id)
    assert cat_entry.category_id == groceries.id


def test_register_single_rule_auto_assigns(db_session):
    checking = _add_account(
        db_session,
        "Auto Assign Checking",
        AccountType.asset,
        AccountSubtype.checking,
    )
    dining = db_session.query(Category).filter(Category.slug == "dining").one()
    expense_acct = db_session.query(Account).filter(Account.slug == "uncategorized_expense").one()
    create_rule(
        db_session,
        pattern="Zelle payment to RADHIKA PATWARDHAN",
        category_id=dining.id,
        amount_direction="outflow",
        apply_to_existing=False,
    )
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 2, 1),
            payee="Zelle payment to RADHIKA PATWARDHAN JPM99ckej76s",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("-50")),
                EntryLine(account_id=expense_acct.id, amount=Decimal("50")),
            ],
        ),
    )
    reg = get_register(db_session, checking.id)
    assert reg.rows[0].category_id == dining.id
    assert reg.rows[0].category_name == dining.name
    assert reg.rows[0].category_suggestions == []
    assert reg.rows[0].category_conflict is False


def test_register_venmo_mixed_directions_conflict(db_session):
    checking = _add_account(
        db_session,
        "Venmo Direction Checking",
        AccountType.asset,
        AccountSubtype.checking,
    )
    cat_a = db_session.query(Category).filter(Category.slug == "groceries").one()
    cat_b = db_session.query(Category).filter(Category.slug == "dining").one()
    expense_acct = db_session.query(Account).filter(Account.slug == "uncategorized_expense").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 8),
            payee="Venmo",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("-159")),
                EntryLine(account_id=expense_acct.id, amount=Decimal("159"), category_id=cat_b.id),
            ],
        ),
    )
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 18),
            payee="Venmo",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("50")),
                EntryLine(account_id=expense_acct.id, amount=Decimal("-50"), category_id=cat_a.id),
            ],
        ),
    )
    reg = get_register(db_session, checking.id)
    assert all(r.category_conflict for r in reg.rows)


def test_register_category_conflict(db_session):
    checking = _add_account(
        db_session,
        "Conflict Checking",
        AccountType.asset,
        AccountSubtype.checking,
    )
    groceries = db_session.query(Category).filter(Category.slug == "groceries").one()
    dining = db_session.query(Category).filter(Category.slug == "dining").one()
    expense_acct = db_session.query(Account).filter(Account.slug == "uncategorized_expense").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 2, 1),
            payee="Venmo Payment ABC",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("-20")),
                EntryLine(account_id=expense_acct.id, amount=Decimal("20"), category_id=groceries.id),
            ],
        ),
    )
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 2, 2),
            payee="Venmo Payment XYZ",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("-30")),
                EntryLine(account_id=expense_acct.id, amount=Decimal("30"), category_id=dining.id),
            ],
        ),
    )
    reg = get_register(db_session, checking.id)
    assert all(r.category_conflict for r in reg.rows)
    assert len(reg.rows) == 2


def test_register_category_suggestions(db_session):
    checking = _add_account(
        db_session,
        "Suggest Checking",
        AccountType.asset,
        AccountSubtype.checking,
    )
    groceries = db_session.query(Category).filter(Category.slug == "groceries").one()
    dining = db_session.query(Category).filter(Category.slug == "dining").one()
    expense_acct = db_session.query(Account).filter(Account.slug == "uncategorized_expense").one()
    create_rule(
        db_session,
        pattern="Venmo",
        category_id=groceries.id,
        amount_direction="outflow",
        apply_to_existing=False,
    )
    create_rule(
        db_session,
        pattern="Venmo",
        category_id=dining.id,
        amount_direction="outflow",
        apply_to_existing=False,
    )
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 2, 1),
            payee="Venmo Payment ABC",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("-20")),
                EntryLine(account_id=expense_acct.id, amount=Decimal("20")),
            ],
        ),
    )
    reg = get_register(db_session, checking.id)
    assert len(reg.rows) == 1
    assert reg.rows[0].category_id is None
    assert len(reg.rows[0].category_suggestions) == 2
    suggestion_ids = {s.category_id for s in reg.rows[0].category_suggestions}
    assert suggestion_ids == {groceries.id, dining.id}


def test_normalize_rule_patterns(db_session):
    dining = db_session.query(Category).filter(Category.slug == "dining").one()
    create_rule(
        db_session,
        pattern="Zelle payment to RADHIKA PATWARDHAN JPM99ckej76s",
        category_id=dining.id,
        apply_to_existing=False,
    )
    updated = normalize_rule_patterns(db_session)
    assert updated == 1
    rule = db_session.query(CategoryRule).one()
    assert rule.pattern == "Zelle payment to RADHIKA PATWARDHAN"


def test_remember_pattern_on_register_row(db_session):
    checking = _add_account(
        db_session,
        "Pattern Checking",
        AccountType.asset,
        AccountSubtype.checking,
    )
    expense_acct = db_session.query(Account).filter(Account.slug == "uncategorized_expense").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 2, 1),
            payee="Zelle payment to RADHIKA PATWARDHAN JPM99ckej76s",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("-50")),
                EntryLine(account_id=expense_acct.id, amount=Decimal("50")),
            ],
        ),
    )
    reg = get_register(db_session, checking.id)
    assert reg.rows[0].remember_pattern == "Zelle payment to RADHIKA PATWARDHAN"
