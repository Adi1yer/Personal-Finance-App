from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.balance_explain import BalanceExplainResponse
from app.schemas.register import RegisterResponse
from app.services.balance_explain import explain_balance
from app.services.register import get_register

router = APIRouter(prefix="/register", tags=["register"])


@router.get("/{account_id}/balance-explain", response_model=BalanceExplainResponse)
def balance_explain(account_id: int, db: Session = Depends(get_db)) -> BalanceExplainResponse:
    try:
        return BalanceExplainResponse(**explain_balance(db, account_id))
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("", response_model=RegisterResponse)
def register(
    account_id: int = Query(...),
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> RegisterResponse:
    try:
        return get_register(db, account_id, limit=limit, offset=offset)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
