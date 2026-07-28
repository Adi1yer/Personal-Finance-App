from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from typing import Optional

from app.models.account import Account, AccountSubtype, AccountType, SyncSource
from app.models.account_mark import AccountMark
from app.models.plaid import PlaidAccount, PlaidItem
from app.schemas.overview import OverviewAccountLine, OverviewGroup, OverviewResponse
from app.services.ledger import all_account_balances
from app.services.register import account_register_pending_count
from app.services.reports.generator import income_statement, month_date_range
from app.services.seed import SYSTEM_ACCOUNT_SLUGS

GROUP_LABELS: dict[str, str] = {
    "cash": "Cash",
    "investments": "Investments",
    "retirement": "Retirement",
    "health": "Health savings",
    "credit_cards": "Credit cards",
    "other_assets": "Other assets",
    "other_liabilities": "Other liabilities",
}

GROUP_ORDER = [
    "cash",
    "investments",
    "retirement",
    "health",
    "other_assets",
    "credit_cards",
    "other_liabilities",
]


def _group_key(acc: Account) -> Optional[str]:
    if acc.account_type == AccountType.asset:
        if acc.subtype == AccountSubtype.checking:
            return "cash"
        if acc.subtype == AccountSubtype.brokerage:
            return "investments"
        if acc.subtype == AccountSubtype.retirement:
            return "retirement"
        if acc.subtype == AccountSubtype.hsa:
            return "health"
        return "other_assets"
    if acc.account_type == AccountType.liability:
        if acc.subtype == AccountSubtype.credit_card:
            return "credit_cards"
        return "other_liabilities"
    return None


def _as_utc(dt: datetime | date | None) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _relative_label(dt: datetime | date | None) -> str:
    normalized = _as_utc(dt)
    if normalized is None:
        return "Never synced"
    now = datetime.now(timezone.utc)
    seconds = int((now - normalized).total_seconds())
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _last_updated(
    db: Session,
    acc: Account,
    plaid_sync: dict[int, datetime | None],
    latest_mark_saved: dict[int, datetime],
) -> tuple[Optional[str], str]:
    if acc.sync_source == SyncSource.plaid and acc.id in plaid_sync:
        ts = plaid_sync[acc.id]
        if ts:
            return ts.isoformat(), _relative_label(ts)
        return None, "Never synced"
    if acc.id in latest_mark_saved:
        ts = latest_mark_saved[acc.id]
        return ts.isoformat(), _relative_label(ts)
    if acc.updated_at:
        return acc.updated_at.isoformat(), _relative_label(acc.updated_at)
    return None, "Manual"


def build_overview(db: Session) -> OverviewResponse:
    from app.config import get_settings
    from app.services.holdings import refresh_live_investment_values

    settings = get_settings()
    if settings.live_market_quotes_enabled:
        refresh_live_investment_values(db)

    today = date.today()
    year, month = today.year, today.month
    start, end = month_date_range(year, month)
    inc = income_statement(db, start, end)

    balances = all_account_balances(db, today)
    accounts = db.scalars(
        select(Account).where(Account.is_active.is_(True)).order_by(Account.name)
    ).all()

    plaid_sync: dict[int, datetime | None] = {}
    for pa in db.scalars(select(PlaidAccount).where(PlaidAccount.account_id.isnot(None))).all():
        item = db.get(PlaidItem, pa.plaid_item_id)
        if item and pa.account_id:
            ts = _as_utc(item.last_synced_at or item.updated_at)
            existing = plaid_sync.get(pa.account_id)
            if existing is None or (ts and (existing is None or ts > existing)):
                plaid_sync[pa.account_id] = ts

    mark_rows = db.execute(
        select(AccountMark.account_id, func.max(AccountMark.as_of_date)).group_by(
            AccountMark.account_id
        )
    ).all()
    latest_mark_as_of = {aid: d for aid, d in mark_rows}
    latest_mark_saved: dict[int, datetime] = {}
    for aid, as_of_d in latest_mark_as_of.items():
        mark = (
            db.query(AccountMark)
            .filter(AccountMark.account_id == aid, AccountMark.as_of_date == as_of_d)
            .order_by(AccountMark.updated_at.desc())
            .first()
        )
        if mark and mark.updated_at:
            latest_mark_saved[aid] = _as_utc(mark.updated_at) or mark.updated_at
        elif mark:
            latest_mark_saved[aid] = _as_utc(as_of_d) or datetime.combine(
                as_of_d, datetime.min.time(), tzinfo=timezone.utc
            )

    buckets: dict[str, list[OverviewAccountLine]] = {k: [] for k in GROUP_ORDER}
    total_assets = Decimal("0")
    total_liabilities = Decimal("0")
    cash_total = Decimal("0")

    for acc in accounts:
        if acc.slug in SYSTEM_ACCOUNT_SLUGS:
            continue
        key = _group_key(acc)
        if key is None:
            continue
        bal = balances.get(acc.id, Decimal("0"))
        if acc.account_type == AccountType.asset:
            total_assets += bal
            if key == "cash":
                cash_total += bal
        elif acc.account_type == AccountType.liability:
            total_liabilities += abs(bal)

        updated_at, label = _last_updated(db, acc, plaid_sync, latest_mark_saved)
        holdings_as_of = None
        quotes_at = None
        if acc.subtype.value in ("brokerage", "retirement", "hsa"):
            holdings_as_of = (
                latest_mark_as_of.get(acc.id).isoformat()
                if acc.id in latest_mark_as_of
                else None
            )
            if acc.id in latest_mark_saved:
                quotes_at = latest_mark_saved[acc.id].isoformat()

        buckets[key].append(
            OverviewAccountLine(
                id=acc.id,
                name=acc.name,
                balance=bal,
                sync_source=acc.sync_source.value,
                subtype=acc.subtype.value,
                last_updated_at=updated_at,
                last_updated_label=label,
                register_pending_count=account_register_pending_count(db, acc.id),
                holdings_as_of=holdings_as_of,
                quotes_refreshed_at=quotes_at,
            )
        )

    groups = []
    for key in GROUP_ORDER:
        lines = buckets[key]
        if not lines:
            continue
        total = sum(
            (abs(l.balance) if key in ("credit_cards", "other_liabilities") else l.balance)
            for l in lines
        )
        groups.append(
            OverviewGroup(
                key=key,
                label=GROUP_LABELS[key],
                total=total,
                accounts=sorted(lines, key=lambda x: x.name.lower()),
            )
        )

    from app.services.annual_goals import get_annual_goals_progress
    from app.services.advisor_service import sync_insights

    return OverviewResponse(
        net_worth=total_assets - total_liabilities,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        groups=groups,
        cash_total=cash_total,
        monthly_expenses=inc.total_expenses,
        goals_progress=get_annual_goals_progress(db),
        advisor_insights=sync_insights(db),
    )
