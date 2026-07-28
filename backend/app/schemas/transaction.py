from __future__ import annotations
from typing import Optional

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.transaction import TransactionSource


class EntryLine(BaseModel):
    account_id: int
    amount: Decimal
    category_id: Optional[int] = None


class EntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    category_id: Optional[int]
    amount: Decimal
    entry_date: date
    is_cleared: bool


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    txn_date: date
    payee: str
    memo: Optional[str]
    source: TransactionSource
    external_id: Optional[str]
    is_transfer: bool
    entries: list[EntryRead] = []


class TransactionCreate(BaseModel):
    txn_date: date
    payee: str = ""
    memo: Optional[str] = None
    external_id: Optional[str] = None
    entries: list[EntryLine] = Field(..., min_length=2)


class TransferCreate(BaseModel):
    txn_date: date
    from_account_id: int
    to_account_id: int
    amount: Decimal = Field(..., gt=0)
    memo: Optional[str] = None


class CardPurchaseCreate(BaseModel):
    txn_date: date
    card_account_id: int
    expense_account_id: int
    category_id: int
    amount: Decimal = Field(..., gt=0)
    payee: str = ""
    memo: Optional[str] = None


class CardPaymentCreate(BaseModel):
    txn_date: date
    checking_account_id: int
    card_account_id: int
    amount: Decimal = Field(..., gt=0)
    memo: Optional[str] = None


class TransactionPatch(BaseModel):
    payee: Optional[str] = None
    memo: Optional[str] = None
    txn_date: Optional[date] = None
