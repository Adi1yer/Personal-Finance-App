from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ReconciliationCreate(BaseModel):
    statement_end_date: date
    ending_balance: Decimal
    cleared_entry_ids: list[int] = []


class ReconciliationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    statement_end_date: date
    ending_balance: Decimal
