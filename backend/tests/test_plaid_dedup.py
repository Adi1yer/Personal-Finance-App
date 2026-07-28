from datetime import date, datetime, timezone
from decimal import Decimal

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.import_staging import ImportStaging, StagingStatus
from app.models.plaid import PlaidAccount, PlaidItem
from app.models.transaction import Transaction, TransactionSource
from app.schemas.transaction import EntryLine, TransactionCreate
from app.services.plaid_dedup import (
    cleanup_satisfied_staging,
    find_pending_staging_duplicate,
    find_plaid_activity_duplicate,
    find_recorded_plaid_activity,
    find_semantic_duplicate,
    normalize_plaid_payee_key,
    repair_duplicate_plaid_transactions,
    staging_already_satisfied,
)
from app.services.posting import create_transaction
from app.services.slug import unique_account_slug


def _checking(db):
    acc = Account(
        name="Dedup Checking",
        slug=unique_account_slug(db, "Dedup Checking"),
        account_type=AccountType.asset,
        subtype=AccountSubtype.checking,
        sync_source=SyncSource.plaid,
    )
    db.add(acc)
    db.flush()
    return acc


def test_normalize_zelle_payee_ignores_case_and_id():
    a = "Zelle payment to ANNA MINDLINA JPM99CO3XP6G"
    b = "Zelle payment to Anna Mindlina JPM99co3xp6g"
    assert normalize_plaid_payee_key(a) == normalize_plaid_payee_key(b)


def test_find_semantic_duplicate_matches_pending_posted_zelle(db_session):
    checking = _checking(db_session)
    income = db_session.query(Account).filter(Account.slug == "salary_income").one()
    pending = create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 7, 2),
            payee="Zelle payment to ANNA MINDLINA JPM99co3xp6g",
            external_id="pending-id",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("-250")),
                EntryLine(account_id=income.id, amount=Decimal("250")),
            ],
        ),
        source=TransactionSource.plaid,
    )
    pending.entries[0].is_cleared = False
    db_session.commit()

    match = find_semantic_duplicate(
        db_session,
        checking.id,
        "ZELLE PAYMENT TO ANNA MINDLINA JPM99CO3XP6G",
        Decimal("-250"),
        date(2026, 7, 2),
    )
    assert match is not None
    assert match.id == pending.id


def test_repair_voids_pending_posted_duplicate(db_session):
    checking = _checking(db_session)
    card = Account(
        name="Dedup Card",
        slug=unique_account_slug(db_session, "Dedup Card"),
        account_type=AccountType.liability,
        subtype=AccountSubtype.credit_card,
        sync_source=SyncSource.plaid,
    )
    db_session.add(card)
    db_session.flush()
    expense = db_session.query(Account).filter(Account.slug == "uncategorized_expense").one()
    income = db_session.query(Account).filter(Account.slug == "salary_income").one()

    pending = create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 30),
            payee="CL *Chase Travel",
            external_id="pending-travel",
            entries=[
                EntryLine(account_id=card.id, amount=Decimal("-658.79")),
                EntryLine(account_id=expense.id, amount=Decimal("658.79")),
            ],
        ),
        source=TransactionSource.plaid,
    )
    posted = create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 7, 2),
            payee="CL *Chase Travel",
            external_id="posted-travel",
            entries=[
                EntryLine(account_id=card.id, amount=Decimal("-658.79")),
                EntryLine(account_id=expense.id, amount=Decimal("658.79")),
            ],
        ),
        source=TransactionSource.plaid,
    )
    posted.entries[0].is_cleared = True
    db_session.commit()

    result = repair_duplicate_plaid_transactions(db_session)
    assert result["voided"] == 1
    db_session.refresh(pending)
    db_session.refresh(posted)
    assert pending.voided_at is not None
    assert posted.voided_at is None

    # Monthly repeats with same amount should survive
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 5, 1),
            payee="LendingClub",
            external_id="lc-may",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("3236.49")),
                EntryLine(account_id=income.id, amount=Decimal("-3236.49")),
            ],
        ),
        source=TransactionSource.plaid,
    )
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 6, 30),
            payee="LendingClub",
            external_id="lc-june",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("3236.49")),
                EntryLine(account_id=income.id, amount=Decimal("-3236.49")),
            ],
        ),
        source=TransactionSource.plaid,
    )
    db_session.commit()
    result2 = repair_duplicate_plaid_transactions(db_session)
    assert result2["voided"] == 0


def test_find_pending_staging_duplicate_blocks_same_batch_dupes(db_session):
    checking = _checking(db_session)
    item = PlaidItem(item_id="dedup-item", access_token_encrypted="enc", institution_name="Bank")
    db_session.add(item)
    db_session.flush()
    plaid_acct = PlaidAccount(
        plaid_item_id=item.id,
        plaid_account_id="plaid-checking",
        name="Checking",
        plaid_type="depository",
        plaid_subtype="checking",
        account_id=checking.id,
    )
    db_session.add(plaid_acct)
    db_session.flush()
    pending = ImportStaging(
        plaid_account_id=plaid_acct.id,
        external_id="pending-zelle",
        txn_date=date(2026, 7, 2),
        amount=Decimal("-250"),
        payee="Zelle payment to ANNA MINDLINA JPM99co3xp6g",
        raw_json="{}",
        status=StagingStatus.pending,
    )
    db_session.add(pending)
    db_session.commit()

    match = find_plaid_activity_duplicate(
        db_session,
        checking.id,
        "ZELLE PAYMENT TO ANNA MINDLINA JPM99CO3XP6G",
        Decimal("-250"),
        date(2026, 7, 2),
        exclude_external_id="posted-zelle",
    )
    assert match is not None
    assert isinstance(match, ImportStaging)
    assert match.id == pending.id


def test_find_pending_staging_duplicate_ignores_self(db_session):
    checking = _checking(db_session)
    item = PlaidItem(item_id="dedup-item-2", access_token_encrypted="enc", institution_name="Bank")
    db_session.add(item)
    db_session.flush()
    plaid_acct = PlaidAccount(
        plaid_item_id=item.id,
        plaid_account_id="plaid-checking-2",
        name="Checking",
        plaid_type="depository",
        plaid_subtype="checking",
        account_id=checking.id,
    )
    db_session.add(plaid_acct)
    db_session.flush()
    pending = ImportStaging(
        plaid_account_id=plaid_acct.id,
        external_id="pending-zelle",
        txn_date=date(2026, 7, 2),
        amount=Decimal("-250"),
        payee="Zelle payment to ANNA MINDLINA JPM99co3xp6g",
        raw_json="{}",
        status=StagingStatus.pending,
    )
    db_session.add(pending)
    db_session.commit()

    match = find_pending_staging_duplicate(
        db_session,
        checking.id,
        "ZELLE PAYMENT TO ANNA MINDLINA JPM99CO3XP6G",
        Decimal("-250"),
        date(2026, 7, 2),
        exclude_staging_id=pending.id,
    )
    assert match is None


def test_find_recorded_plaid_activity_includes_voided(db_session):
    checking = _checking(db_session)
    income = db_session.query(Account).filter(Account.slug == "salary_income").one()
    voided = create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 7, 2),
            payee="Zelle payment to ANNA MINDLINA JPM99co3xp6g",
            external_id="voided-anna",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("-250")),
                EntryLine(account_id=income.id, amount=Decimal("250")),
            ],
        ),
        source=TransactionSource.plaid,
    )
    voided.voided_at = datetime.now(timezone.utc)
    db_session.commit()

    recorded = find_recorded_plaid_activity(
        db_session,
        checking.id,
        "ZELLE PAYMENT TO ANNA MINDLINA JPM99CO3XP6G",
        Decimal("-250"),
        date(2026, 7, 2),
    )
    assert recorded is not None
    assert recorded.id == voided.id


def test_repair_restores_voided_cluster_keeper(db_session):
    checking = _checking(db_session)
    expense = db_session.query(Account).filter(Account.slug == "uncategorized_expense").one()
    txns = []
    for ext in ["dup-a", "dup-b"]:
        txn = create_transaction(
            db_session,
            TransactionCreate(
                txn_date=date(2026, 7, 2),
                payee="Itr Concession Company Ll",
                external_id=ext,
                entries=[
                    EntryLine(account_id=checking.id, amount=Decimal("-4.80")),
                    EntryLine(account_id=expense.id, amount=Decimal("4.80")),
                ],
            ),
            source=TransactionSource.plaid,
        )
        txns.append(txn)
    db_session.commit()

    result = repair_duplicate_plaid_transactions(db_session)
    assert result["voided"] == 1
    assert result["restored"] == 0
    active = (
        db_session.query(Transaction)
        .filter(Transaction.payee == "Itr Concession Company Ll", Transaction.voided_at.is_(None))
        .count()
    )
    assert active == 1


def test_cleanup_satisfied_staging_marks_posted_orphans_skipped(db_session):
    checking = _checking(db_session)
    income = db_session.query(Account).filter(Account.slug == "salary_income").one()
    create_transaction(
        db_session,
        TransactionCreate(
            txn_date=date(2026, 7, 2),
            payee="Zelle payment to ANNA MINDLINA JPM99co3xp6g",
            external_id="keeper-anna",
            entries=[
                EntryLine(account_id=checking.id, amount=Decimal("-250")),
                EntryLine(account_id=income.id, amount=Decimal("250")),
            ],
        ),
        source=TransactionSource.plaid,
    )
    from app.models.plaid import PlaidAccount, PlaidItem

    item = PlaidItem(item_id="stg-item", access_token_encrypted="enc", institution_name="Bank")
    db_session.add(item)
    db_session.flush()
    plaid_acct = PlaidAccount(
        plaid_item_id=item.id,
        plaid_account_id="plaid-checking-stg",
        name="Checking",
        plaid_type="depository",
        plaid_subtype="checking",
        account_id=checking.id,
    )
    db_session.add(plaid_acct)
    db_session.flush()
    row = ImportStaging(
        plaid_account_id=plaid_acct.id,
        external_id="orphan-anna",
        txn_date=date(2026, 7, 2),
        amount=Decimal("-250"),
        payee="ZELLE PAYMENT TO ANNA MINDLINA JPM99CO3XP6G",
        raw_json="{}",
        status=StagingStatus.posted,
    )
    db_session.add(row)
    db_session.commit()

    assert staging_already_satisfied(db_session, row)
    result = cleanup_satisfied_staging(db_session)
    assert result["skipped"] == 1
    db_session.refresh(row)
    assert row.status == StagingStatus.skipped
