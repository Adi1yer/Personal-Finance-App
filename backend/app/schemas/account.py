from __future__ import annotations
from datetime import date
from typing import Optional

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.account import AccountSubtype, AccountType, SyncSource


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    institution_id: Optional[int]
    name: str
    slug: str
    account_type: AccountType
    subtype: AccountSubtype
    sync_source: SyncSource
    is_active: bool
    balance: Optional[Decimal] = None


class AccountCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    account_type: AccountType
    subtype: AccountSubtype = AccountSubtype.other
    sync_source: SyncSource = SyncSource.manual
    institution_id: Optional[int] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    account_type: Optional[AccountType] = None
    subtype: Optional[AccountSubtype] = None
    institution_id: Optional[int] = None
    sync_source: Optional[SyncSource] = None
    tracking_start_date: Optional[date] = None


class AccountMarkCreate(BaseModel):
    account_id: int
    as_of_date: str
    market_value: Decimal
    note: Optional[str] = None
    # Year-to-date total contributions for this account (not an incremental add).
    total_contributions: Optional[Decimal] = None
    # Deprecated alias accepted for older clients.
    contribution_amount: Optional[Decimal] = None


class AccountMarkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    as_of_date: str
    market_value: Decimal
    note: Optional[str]


class AccountContributionCreate(BaseModel):
    account_id: int
    amount: Decimal
    txn_date: str
    memo: Optional[str] = None
