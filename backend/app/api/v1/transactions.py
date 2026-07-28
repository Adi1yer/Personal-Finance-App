from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models.entry import Entry
from app.models.transaction import Transaction, TransactionSource
from app.schemas.transaction import (
    CardPaymentCreate,
    CardPurchaseCreate,
    TransactionCreate,
    TransactionPatch,
    TransactionRead,
    TransferCreate,
)
from app.services.posting import (
    PostingError,
    create_card_payment,
    create_card_purchase,
    create_transaction,
    create_transfer,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionRead])
def list_transactions(
    account_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> list[Transaction]:
    q = db.query(Transaction).options(joinedload(Transaction.entries))
    if account_id:
        q = q.join(Transaction.entries).filter(Entry.account_id == account_id)
    return q.order_by(Transaction.txn_date.desc()).limit(500).all()


@router.post("", response_model=TransactionRead, status_code=201)
def post_transaction(body: TransactionCreate, db: Session = Depends(get_db)) -> Transaction:
    try:
        return create_transaction(db, body)
    except PostingError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/transfer", response_model=TransactionRead, status_code=201)
def post_transfer(body: TransferCreate, db: Session = Depends(get_db)) -> Transaction:
    try:
        return create_transfer(
            db,
            body.txn_date,
            body.from_account_id,
            body.to_account_id,
            body.amount,
            body.memo,
        )
    except PostingError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/card-purchase", response_model=TransactionRead, status_code=201)
def post_card_purchase(body: CardPurchaseCreate, db: Session = Depends(get_db)) -> Transaction:
    try:
        return create_card_purchase(
            db,
            body.txn_date,
            body.card_account_id,
            body.category_id,
            body.amount,
            body.payee,
            body.memo,
            body.expense_account_id,
        )
    except PostingError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/card-payment", response_model=TransactionRead, status_code=201)
def post_card_payment(body: CardPaymentCreate, db: Session = Depends(get_db)) -> Transaction:
    try:
        return create_card_payment(
            db,
            body.txn_date,
            body.checking_account_id,
            body.card_account_id,
            body.amount,
            body.memo,
        )
    except PostingError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/{transaction_id}", response_model=TransactionRead)
def get_transaction(transaction_id: int, db: Session = Depends(get_db)) -> Transaction:
    txn = (
        db.query(Transaction)
        .options(joinedload(Transaction.entries))
        .filter(Transaction.id == transaction_id)
        .first()
    )
    if not txn:
        raise HTTPException(404, "Transaction not found")
    return txn


@router.patch("/{transaction_id}", response_model=TransactionRead)
def patch_transaction(
    transaction_id: int,
    body: TransactionPatch,
    db: Session = Depends(get_db),
) -> Transaction:
    txn = (
        db.query(Transaction)
        .options(joinedload(Transaction.entries))
        .filter(Transaction.id == transaction_id)
        .first()
    )
    if not txn:
        raise HTTPException(404, "Transaction not found")
    if body.payee is not None:
        txn.payee = body.payee
    if body.memo is not None:
        txn.memo = body.memo
    if body.txn_date is not None:
        txn.txn_date = body.txn_date
        for entry in txn.entries:
            entry.entry_date = body.txn_date
    db.commit()
    db.refresh(txn)
    return txn


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)) -> None:
    txn = db.get(Transaction, transaction_id)
    if not txn:
        raise HTTPException(404, "Transaction not found")
    if txn.source != TransactionSource.manual:
        raise HTTPException(400, "Only manual transactions can be deleted")
    db.delete(txn)
    db.commit()
