from __future__ import annotations
from typing import Optional

from decimal import Decimal

from pydantic import BaseModel


class BalanceSheetLine(BaseModel):
    account_id: int
    account_name: str
    account_type: str
    balance: Decimal


class BalanceSheetReport(BaseModel):
    as_of: str
    assets: list[BalanceSheetLine]
    liabilities: list[BalanceSheetLine]
    equity: list[BalanceSheetLine]
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal
    net_worth: Decimal


class IncomeStatementLine(BaseModel):
    account_id: int
    account_name: str
    account_type: str
    total: Decimal


class IncomeStatementReport(BaseModel):
    start: str
    end: str
    income: list[IncomeStatementLine]
    expenses: list[IncomeStatementLine]
    total_income: Decimal
    total_expenses: Decimal
    net_income: Decimal


class CashFlowLine(BaseModel):
    label: str
    amount: Decimal


class CashFlowReport(BaseModel):
    start: str
    end: str
    operating: list[CashFlowLine]
    investing: list[CashFlowLine]
    financing: list[CashFlowLine]
    net_operating: Decimal
    net_investing: Decimal
    net_financing: Decimal
    net_change: Decimal


class QuarterlyMetrics(BaseModel):
    year: int
    quarter: int
    start: str
    end: str
    net_worth: Decimal
    prior_net_worth: Optional[Decimal]
    net_worth_change: Optional[Decimal]
    total_income: Decimal
    total_expenses: Decimal
    net_income: Decimal
    savings_rate: Optional[Decimal]
    spending_by_category: list[dict]


class MonthlyMetrics(BaseModel):
    year: int
    month: int
    start: str
    end: str
    total_income: Decimal
    total_expenses: Decimal
    net_income: Decimal
    prior_total_income: Decimal
    prior_total_expenses: Decimal
    prior_net_income: Decimal
    spending_by_category: list[dict]


class NetWorthHistoryPoint(BaseModel):
    date: str
    net_worth: Decimal
    total_assets: Decimal
    total_liabilities: Decimal


class NetWorthHistoryReport(BaseModel):
    start: str
    end: str
    points: list[NetWorthHistoryPoint]
