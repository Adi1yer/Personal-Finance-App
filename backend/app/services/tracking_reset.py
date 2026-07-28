from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.holding import Holding
from app.models.transaction import Transaction
from app.services.investment_baseline import BASELINE_PREFIX
from app.services.opening_balances import OPENING_EXTERNAL_PREFIX, seed_opening_balances
from app.services.plaid_sync import sync_investment_holdings
from app.services.seed import DEFAULT_TRACKING_START, SYSTEM_ACCOUNT_SLUGS

CUTOFF = DEFAULT_TRACKING_START


def reset_tracking_start(db: Session) -> dict[str, int]:
    """Void pre-cutoff txns, reset tracking date, and reseed opening/baseline positions."""
    accounts_updated = 0
    for acc in db.query(Account).filter(Account.is_active.is_(True)).all():
        if acc.slug in SYSTEM_ACCOUNT_SLUGS:
            continue
        acc.tracking_start_date = CUTOFF
        accounts_updated += 1

    deleted_special = 0
    for txn in db.query(Transaction).all():
        ext = txn.external_id or ""
        if ext.startswith(OPENING_EXTERNAL_PREFIX) or ext.startswith(BASELINE_PREFIX):
            for entry in list(txn.entries):
                db.delete(entry)
            db.delete(txn)
            deleted_special += 1

    voided = 0
    for txn in db.query(Transaction).filter(Transaction.voided_at.is_(None)).all():
        if txn.txn_date >= CUTOFF:
            continue
        txn.voided_at = datetime.now(timezone.utc)
        if txn.external_id:
            txn.external_id = None
        voided += 1

    db.query(Holding).delete()

    db.commit()

    opening = seed_opening_balances(db)
    from app.services.investment_baseline import seed_investment_baseline

    baseline = seed_investment_baseline(db)

    holdings_sync = {"holdings_updated": 0}
    try:
        holdings_sync = sync_investment_holdings(db)
    except Exception:
        pass

    return {
        "accounts_updated": accounts_updated,
        "deleted_opening_baseline": deleted_special,
        "voided_pre_cutoff": voided,
        **opening,
        **{f"baseline_{k}": v for k, v in baseline.items()},
        **holdings_sync,
    }
