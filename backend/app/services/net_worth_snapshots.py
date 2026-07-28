"""Capture daily net worth snapshots after sync."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.net_worth_snapshot import NetWorthSnapshot
from app.services.overview import build_overview

_ASSET_GROUPS = frozenset({"cash", "investments", "retirement", "health", "other_assets"})
_LIABILITY_GROUPS = frozenset({"credit_cards", "other_liabilities"})


def capture_snapshot(db: Session, snapshot_date: date | None = None) -> dict[str, str]:
    overview = build_overview(db)
    snap_date = snapshot_date or date.today()
    by_group = {g.key: str(g.total) for g in overview.groups}
    payload = {
        "groups": by_group,
        "total_assets": str(overview.total_assets),
        "total_liabilities": str(overview.total_liabilities),
    }
    total = overview.net_worth

    existing = (
        db.query(NetWorthSnapshot)
        .filter(NetWorthSnapshot.snapshot_date == snap_date)
        .first()
    )
    if existing:
        existing.total = total
        existing.by_group_json = json.dumps(payload)
    else:
        db.add(
            NetWorthSnapshot(
                snapshot_date=snap_date,
                total=total,
                by_group_json=json.dumps(payload),
            )
        )
    db.commit()
    return {"snapshot_date": snap_date.isoformat(), "total": str(total)}


def _parse_snapshot_payload(raw: str) -> tuple[dict[str, str], Decimal, Decimal]:
    data = json.loads(raw or "{}")
    if isinstance(data, dict) and "groups" in data:
        groups = {str(k): str(v) for k, v in (data.get("groups") or {}).items()}
        assets = Decimal(str(data.get("total_assets") or "0"))
        liabilities = Decimal(str(data.get("total_liabilities") or "0"))
        return groups, assets, liabilities

    # Legacy format: flat group map (total was incorrectly assets+|liabilities|)
    groups = {str(k): str(v) for k, v in (data or {}).items()}
    assets = sum(
        (Decimal(v) for k, v in groups.items() if k in _ASSET_GROUPS),
        Decimal("0"),
    )
    liabilities = sum(
        (Decimal(v) for k, v in groups.items() if k in _LIABILITY_GROUPS),
        Decimal("0"),
    )
    return groups, assets, liabilities


def list_snapshots(db: Session, limit: int = 365) -> list[dict[str, str]]:
    rows = (
        db.query(NetWorthSnapshot)
        .order_by(NetWorthSnapshot.snapshot_date.desc())
        .limit(limit)
        .all()
    )
    out: list[dict[str, str]] = []
    for r in reversed(rows):
        groups, assets, liabilities = _parse_snapshot_payload(r.by_group_json or "{}")
        out.append(
            {
                "snapshot_date": r.snapshot_date.isoformat(),
                "total": str(r.total),
                "by_group": groups,
                "total_assets": str(assets),
                "total_liabilities": str(liabilities),
            }
        )
    return out
