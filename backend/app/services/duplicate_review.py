"""Suspected duplicate transaction clusters for manual review."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.account import Account
from app.models.entry import Entry
from app.models.transaction import Transaction
from app.services.plaid_dedup import _is_system_txn, normalize_plaid_payee_key

CLUSTER_TOLERANCE_DAYS = 7


def _amount_key(amount: Decimal) -> Decimal:
    return abs(Decimal(str(amount))).quantize(Decimal("0.01"))


def _cluster_key(account_id: int, payee_key: str, amount: Decimal) -> tuple[int, str, Decimal]:
    return (account_id, payee_key, _amount_key(amount))


def _find_clusters(db: Session) -> list[dict[str, Any]]:
    txns = (
        db.query(Transaction)
        .options(joinedload(Transaction.entries))
        .filter(Transaction.voided_at.is_(None))
        .all()
    )
    buckets: dict[tuple[int, str, Decimal], list[tuple[Transaction, Entry]]] = defaultdict(list)
    for txn in txns:
        if _is_system_txn(txn):
            continue
        payee_key = normalize_plaid_payee_key(txn.payee or "")
        for entry in txn.entries:
            acc = db.get(Account, entry.account_id)
            if not acc:
                continue
            if acc.subtype.value not in ("checking", "credit_card", "brokerage", "retirement"):
                continue
            buckets[_cluster_key(entry.account_id, payee_key, entry.amount)].append((txn, entry))

    clusters: list[dict[str, Any]] = []
    cluster_id = 0
    for (account_id, payee_key, amount), pairs in buckets.items():
        if len(pairs) < 2:
            continue
        pairs.sort(key=lambda p: (p[0].txn_date, p[0].id))
        grouped: list[list[tuple[Transaction, Entry]]] = [[pairs[0]]]
        for pair in pairs[1:]:
            prev_date = grouped[-1][-1][0].txn_date
            if pair[0].txn_date - prev_date <= timedelta(days=CLUSTER_TOLERANCE_DAYS):
                grouped[-1].append(pair)
            else:
                grouped.append([pair])
        for group in grouped:
            if len(group) < 2:
                continue
            cluster_id += 1
            acc = db.get(Account, account_id)
            reasons = []
            cleared = [p for p in group if p[1].is_cleared]
            pending = [p for p in group if not p[1].is_cleared]
            if cleared and pending:
                reasons.append("pending_to_posted")
            if len({p[0].source.value for p in group}) > 1:
                reasons.append("cross_post")
            if not reasons:
                reasons.append("same_payee_amount")
            clusters.append(
                {
                    "id": cluster_id,
                    "account_id": account_id,
                    "account_name": acc.name if acc else "",
                    "payee_key": payee_key,
                    "amount": str(amount),
                    "confidence": "high" if "pending_to_posted" in reasons else "medium",
                    "reasons": reasons,
                    "transactions": [
                        {
                            "transaction_id": txn.id,
                            "entry_id": entry.id,
                            "txn_date": txn.txn_date.isoformat(),
                            "payee": txn.payee,
                            "amount": str(entry.amount),
                            "is_cleared": entry.is_cleared,
                            "source": txn.source.value,
                        }
                        for txn, entry in group
                    ],
                }
            )
    return clusters


def count_suspected_clusters(db: Session) -> int:
    return len(_find_clusters(db))


def list_suspected_clusters(db: Session) -> list[dict[str, Any]]:
    return _find_clusters(db)


def merge_cluster(db: Session, cluster_id: int, keep_transaction_id: int) -> dict[str, int]:
    clusters = _find_clusters(db)
    cluster = next((c for c in clusters if c["id"] == cluster_id), None)
    if not cluster:
        raise ValueError("Cluster not found")
    voided = 0
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    for item in cluster["transactions"]:
        tid = item["transaction_id"]
        if tid == keep_transaction_id:
            continue
        txn = db.get(Transaction, tid)
        if txn and txn.voided_at is None:
            txn.voided_at = now
            voided += 1
    db.commit()
    return {"voided": voided, "kept": keep_transaction_id}


def keep_both(db: Session, cluster_id: int) -> dict[str, str]:
    clusters = _find_clusters(db)
    cluster = next((c for c in clusters if c["id"] == cluster_id), None)
    if not cluster:
        raise ValueError("Cluster not found")
    return {"status": "kept_both", "cluster_id": str(cluster_id)}
