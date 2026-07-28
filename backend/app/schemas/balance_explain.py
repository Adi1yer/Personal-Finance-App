from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class BalanceExplainResponse(BaseModel):
    account_id: int
    account_name: str
    ledger_balance: str
    plaid_balance: Optional[str] = None
    delta: Optional[str] = None
    opening_balance: str
    uncleared_total: str
    uncleared_count: int
    recent_voids: list[dict]
    cross_post_candidates: list[dict]
    hints: list[str]
