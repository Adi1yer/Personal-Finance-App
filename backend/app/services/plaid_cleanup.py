"""Remove Plaid connections and imported transactions (e.g. sandbox) while keeping ledger accounts."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.account import Account, SyncSource
from app.models.entry import Entry
from app.models.import_staging import ImportStaging
from app.models.plaid import PlaidAccount, PlaidItem
from app.models.transaction import Transaction, TransactionSource


def reset_plaid_data(db: Session) -> dict[str, int]:
    """Delete Plaid items, staging rows, and posted Plaid transactions. Keeps user accounts."""
    plaid_txns = (
        db.query(Transaction).filter(Transaction.source == TransactionSource.plaid).all()
    )
    txn_ids = [t.id for t in plaid_txns]
    entries_deleted = 0
    if txn_ids:
        entries_deleted = (
            db.query(Entry).filter(Entry.transaction_id.in_(txn_ids)).delete(synchronize_session=False)
        )
        db.query(Transaction).filter(Transaction.id.in_(txn_ids)).delete(synchronize_session=False)

    staging_deleted = db.query(ImportStaging).delete()
    accounts_unmapped = 0
    for pa in db.query(PlaidAccount).all():
        if pa.account_id:
            acc = db.get(Account, pa.account_id)
            if acc:
                acc.sync_source = SyncSource.manual
            accounts_unmapped += 1

    plaid_accounts_deleted = db.query(PlaidAccount).delete()
    plaid_items_deleted = db.query(PlaidItem).delete()
    db.commit()

    return {
        "transactions_deleted": len(txn_ids),
        "entries_deleted": entries_deleted,
        "staging_deleted": staging_deleted,
        "accounts_unmapped": accounts_unmapped,
        "plaid_accounts_deleted": plaid_accounts_deleted,
        "plaid_items_deleted": plaid_items_deleted,
    }
