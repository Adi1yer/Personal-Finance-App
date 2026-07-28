"""Post-sync health summary and current ledger warnings."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.account import Account, AccountSubtype
from app.models.import_staging import ImportStaging, StagingStatus
from app.models.plaid import PlaidAccount
from app.models.transaction import Transaction
from app.services.ledger import account_balance
from app.services.plaid_dedup import normalize_plaid_payee_key
from app.services.profile_settings import get_setting, set_setting


def _balance_mismatches(db: Session) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    plaid_accounts = db.query(PlaidAccount).filter(PlaidAccount.account_id.isnot(None)).all()
    for pa in plaid_accounts:
        if pa.balance_current is None or not pa.account_id:
            continue
        acc = db.get(Account, pa.account_id)
        if not acc or acc.subtype not in (
            AccountSubtype.checking,
            AccountSubtype.credit_card,
            AccountSubtype.brokerage,
            AccountSubtype.retirement,
            AccountSubtype.hsa,
        ):
            continue
        ledger = account_balance(db, pa.account_id)
        plaid = Decimal(str(pa.balance_current))
        delta = ledger - plaid
        if abs(delta) >= Decimal("0.02"):
            mismatches.append(
                {
                    "account_id": pa.account_id,
                    "account_name": acc.name,
                    "ledger_balance": str(ledger),
                    "plaid_balance": str(plaid),
                    "delta": str(delta),
                }
            )
    return mismatches


def _staging_orphans(db: Session) -> int:
    return (
        db.query(ImportStaging)
        .filter(ImportStaging.status == StagingStatus.pending)
        .count()
    )


def build_health_summary(db: Session, sync_result: dict[str, Any] | None = None) -> dict[str, Any]:
    from app.services.duplicate_review import count_suspected_clusters

    dupes = count_suspected_clusters(db)
    mismatches = _balance_mismatches(db)
    staging_pending = _staging_orphans(db)

    warnings: list[str] = []
    if dupes > 0:
        warnings.append(f"{dupes} suspected duplicate cluster(s) need review")
    if mismatches:
        warnings.append(f"{len(mismatches)} account balance mismatch(es)")
    if staging_pending > 10:
        warnings.append(f"{staging_pending} pending staging rows")

    sync = sync_result or get_setting(db, "last_sync_health") or {}
    health = {
        "ok": dupes == 0 and not mismatches,
        "suspected_duplicate_clusters": dupes,
        "balance_mismatches": mismatches,
        "staging_pending": staging_pending,
        "warnings": warnings,
        "sync": {
            "ran": sync.get("ran", False),
            "posted": sync.get("posted", 0),
            "staged": sync.get("staged", 0),
            "skipped": sync.get("skipped", 0),
            "investment_posted": sync.get("investment_posted", 0),
            "holdings_updated": sync.get("holdings_updated", 0),
            "plaid_duplicate_repair": _nested_count(sync, "plaid_duplicate_repair", "voided"),
            "staging_cleanup": _nested_count(sync, "staging_cleanup", "marked_skipped"),
            "live_quotes_fetched": sync.get("live_quotes_fetched", 0),
            "opening_created": sync.get("opening_created", 0),
            "opening_updated": sync.get("opening_updated", 0),
        },
    }
    return health


def _nested_count(sync: dict[str, Any], key: str, subkey: str) -> int:
    val = sync.get(key)
    if isinstance(val, dict):
        return int(val.get(subkey, 0) or 0)
    return 0


def store_sync_health(db: Session, sync_result: dict[str, Any]) -> dict[str, Any]:
    set_setting(db, "last_sync_health", sync_result)
    return build_health_summary(db, sync_result)
