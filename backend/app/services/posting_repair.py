from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.account import Account, AccountSubtype, AccountType
from app.models.import_staging import ImportStaging, StagingStatus
from app.models.transaction import Transaction, TransactionSource
from app.services.categorization import is_card_payment, parse_plaid_raw
from app.services.plaid_dedup import staging_already_satisfied, staging_has_live_ledger_match


def _txn_has_checking_card_cross_post(db: Session, txn: Transaction) -> bool:
    checking_entries = []
    card_entries = []
    expense_entries = []
    for entry in txn.entries:
        acc = db.get(Account, entry.account_id)
        if not acc:
            continue
        if acc.subtype == AccountSubtype.checking:
            checking_entries.append(entry)
        elif acc.subtype == AccountSubtype.credit_card:
            card_entries.append(entry)
        elif acc.account_type == AccountType.expense:
            expense_entries.append(entry)
    return bool(checking_entries and card_entries and not expense_entries)


def _is_legitimate_card_payment(db: Session, txn: Transaction) -> bool:
    staging = None
    if txn.external_id:
        staging = (
            db.query(ImportStaging)
            .filter(ImportStaging.external_id == txn.external_id)
            .first()
        )
    raw = parse_plaid_raw(staging.raw_json if staging else None)
    fallback_amount = staging.amount if staging else 0
    plaid_amount = float(raw.get("amount", fallback_amount))
    return is_card_payment(raw, plaid_amount, payee=txn.payee or "")


def repair_card_cross_posted_transactions(db: Session) -> dict[str, int]:
    """
    Void Plaid card purchases/credits wrongly posted to checking + card.
    Re-queue orphaned staging rows and repost with correct expense + card entries.
    """
    voided = requeued = 0
    external_ids: list[str] = []

    txns = (
        db.query(Transaction)
        .filter(
            Transaction.source == TransactionSource.plaid,
            Transaction.voided_at.is_(None),
        )
        .all()
    )

    for txn in txns:
        if not _txn_has_checking_card_cross_post(db, txn):
            continue
        if _is_legitimate_card_payment(db, txn):
            continue

        txn.voided_at = datetime.now(timezone.utc)
        if txn.external_id:
            external_ids.append(txn.external_id)
            txn.external_id = None
        voided += 1

    for row in db.query(ImportStaging).filter(ImportStaging.status == StagingStatus.posted).all():
        active = (
            db.query(Transaction)
            .filter(
                Transaction.external_id == row.external_id,
                Transaction.voided_at.is_(None),
            )
            .first()
        )
        if active:
            continue
        if staging_has_live_ledger_match(db, row) or staging_already_satisfied(db, row):
            row.status = StagingStatus.skipped
            continue
        row.status = StagingStatus.pending
        requeued += 1
        if row.external_id not in external_ids:
            external_ids.append(row.external_id)

    if voided or requeued:
        db.commit()

    posted = 0
    has_pending = (
        db.query(ImportStaging)
        .filter(ImportStaging.status == StagingStatus.pending)
        .first()
    )
    if has_pending:
        from app.models.plaid import PlaidItem
        from app.services.plaid_sync import _post_staged_for_item

        for item in db.query(PlaidItem).all():
            posted += _post_staged_for_item(db, item)

    return {"voided": voided, "requeued": requeued, "reposted": posted}
