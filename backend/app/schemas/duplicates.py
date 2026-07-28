from __future__ import annotations

from pydantic import BaseModel


class DuplicateTxnItem(BaseModel):
    transaction_id: int
    entry_id: int
    txn_date: str
    payee: str
    amount: str
    is_cleared: bool
    source: str


class DuplicateCluster(BaseModel):
    id: int
    account_id: int
    account_name: str
    payee_key: str
    amount: str
    confidence: str
    reasons: list[str]
    transactions: list[DuplicateTxnItem]


class MergeDuplicateRequest(BaseModel):
    keep_transaction_id: int
