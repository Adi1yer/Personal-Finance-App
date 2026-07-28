from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class OverviewAccountLine(BaseModel):
    id: int
    name: str
    balance: Decimal
    sync_source: str
    subtype: str
    last_updated_at: Optional[str]
    last_updated_label: str
    register_pending_count: int = 0
    holdings_as_of: Optional[str] = None
    quotes_refreshed_at: Optional[str] = None


class OverviewGroup(BaseModel):
    key: str
    label: str
    total: Decimal
    accounts: list[OverviewAccountLine]


class OverviewResponse(BaseModel):
    net_worth: Decimal
    total_assets: Decimal
    total_liabilities: Decimal
    groups: list[OverviewGroup]
    cash_total: Decimal
    monthly_expenses: Decimal
    goals_progress: Optional[dict] = None
    advisor_insights: Optional[list[str]] = None
