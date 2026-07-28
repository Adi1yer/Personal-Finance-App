from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.transaction import TransactionSource


class CategorySuggestion(BaseModel):
    category_id: int
    category_name: str
    rule_id: Optional[int] = None
    label: Optional[str] = None


class HoldingSummary(BaseModel):
    ticker: str
    security_name: str
    quantity: Decimal
    cost_basis_total: Decimal
    market_value: Decimal
    gain: Decimal


class RegisterRow(BaseModel):
    entry_id: int
    transaction_id: int
    txn_date: date
    payee: str
    memo: Optional[str]
    charge: Optional[Decimal]
    payment: Optional[Decimal]
    running_balance: Decimal
    category_id: Optional[int]
    category_name: Optional[str]
    category_suggestions: list[CategorySuggestion] = []
    remember_pattern: Optional[str] = None
    category_conflict: bool = False
    activity_label: Optional[str] = None
    cash_direction: Optional[str] = None
    is_cleared: bool
    is_transfer: bool
    source: str
    investment_type: Optional[str]
    investment_subtype: Optional[str]
    security_name: Optional[str]
    quantity: Optional[Decimal]
    price: Optional[Decimal]


class RegisterResponse(BaseModel):
    account_id: int
    account_name: str
    account_subtype: str
    amount_out_label: str
    amount_in_label: str
    balance_column_label: str = "Balance"
    tracking_start_date: Optional[date]
    opening_balance: Decimal
    current_balance: Decimal
    cash_balance: Optional[Decimal] = None
    portfolio_value: Optional[Decimal] = None
    holdings: list[HoldingSummary] = []
    holdings_as_of_date: Optional[date] = None
    cleared_balance: Decimal
    uncleared_balance: Decimal
    uncleared_count: int
    plaid_balance_current: Optional[Decimal] = None
    total_count: int
    rows: list[RegisterRow]


class EntryPatch(BaseModel):
    category_id: Optional[int] = None
    is_cleared: Optional[bool] = None


class TransactionPatch(BaseModel):
    payee: Optional[str] = None
    memo: Optional[str] = None
    txn_date: Optional[date] = None


class CategoryRuleCreate(BaseModel):
    pattern: str
    category_id: int
    match_field: str = "payee"
    priority: int = 10
    amount_direction: str = "any"


class CategoryRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pattern: str
    category_id: int
    category_name: Optional[str] = None
    match_field: str
    priority: int
    amount_direction: str = "any"
    transactions_updated: int = 0


class CategoryRuleUpdate(BaseModel):
    pattern: Optional[str] = None
    category_id: Optional[int] = None
    match_field: Optional[str] = None
    priority: Optional[int] = None
    amount_direction: Optional[str] = None
