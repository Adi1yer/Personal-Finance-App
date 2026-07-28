from __future__ import annotations
from typing import Any, Optional

from pydantic import BaseModel


class LinkTokenResponse(BaseModel):
    link_token: str
    redirect_uri: Optional[str] = None


class LinkTokenRequest(BaseModel):
    redirect_uri: Optional[str] = None


class PlaidBrowserLinkResponse(BaseModel):
    opened: bool
    url: str
    browser: str = "default"


class PlaidBrowserSessionResponse(BaseModel):
    link_token: str


class PublicTokenExchange(BaseModel):
    public_token: str


class PlaidExchangeResponse(BaseModel):
    item_id: str
    institution_name: Optional[str] = None


class SyncHealthSync(BaseModel):
    ran: bool = False
    posted: int = 0
    staged: int = 0
    skipped: int = 0
    investment_posted: int = 0
    holdings_updated: int = 0
    plaid_duplicate_repair: int = 0
    staging_cleanup: int = 0
    live_quotes_fetched: int = 0
    opening_created: int = 0
    opening_updated: int = 0


class BalanceMismatch(BaseModel):
    account_id: int
    account_name: str
    ledger_balance: str
    plaid_balance: str
    delta: str


class SyncHealthResponse(BaseModel):
    ok: bool
    suspected_duplicate_clusters: int
    balance_mismatches: list[BalanceMismatch]
    staging_pending: int
    warnings: list[str]
    sync: SyncHealthSync


class PlaidSyncResponse(BaseModel):
    ran: bool = True
    staged: int = 0
    posted: int = 0
    skipped: int = 0
    investment_staged: int = 0
    investment_posted: int = 0
    investment_skipped: int = 0
    holdings_updated: int = 0
    cutoff_skipped: int = 0
    live_quotes_fetched: int = 0
    live_prices_updated: int = 0
    live_accounts_updated: int = 0
    opening_created: int = 0
    opening_updated: int = 0
    health: Optional[SyncHealthResponse] = None


class PlaidStatusResponse(BaseModel):
    enabled: bool
    configured: bool
    env: str
    item_count: int
    transactions_sync_days: int = 7
    holdings_sync_days: int = 30
    cloud_scheduler_enabled: bool = False
    last_transactions_sync_at: Optional[str] = None
    last_holdings_sync_at: Optional[str] = None


class PlaidAccountRead(BaseModel):
    id: int
    plaid_account_id: str
    name: str
    official_name: Optional[str] = None
    mask: Optional[str] = None
    balance_current: Optional[str] = None
    plaid_type: Optional[str] = None
    plaid_subtype: Optional[str] = None
    institution_name: Optional[str] = None
    ledger_account_id: Optional[int] = None
    ledger_account_name: Optional[str] = None


class PlaidResetResponse(BaseModel):
    transactions_deleted: int
    entries_deleted: int
    staging_deleted: int
    accounts_unmapped: int
    plaid_accounts_deleted: int
    plaid_items_deleted: int


class PlaidMapRequest(BaseModel):
    ledger_account_id: Optional[int] = None
    create_ledger_account: bool = False
    ledger_account_name: Optional[str] = None
    account_type: Optional[str] = None
    subtype: Optional[str] = None
