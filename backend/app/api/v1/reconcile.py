from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.account import Account
from app.schemas.reconciliation import ReconciliationCreate, ReconciliationRead
from app.services.reconciliation import create_reconciliation, reconciliation_preview
from app.services.reports import reports_readiness
from app.services.reports.export import export_quarter_package

router = APIRouter(prefix="/reconcile", tags=["reconciliation"])


@router.get("/{account_id}/preview")
def reconcile_preview(
    account_id: int,
    statement_end_date: date = Query(...),
    ending_balance: Decimal = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    if not db.get(Account, account_id):
        raise HTTPException(404, "Account not found")
    try:
        return reconciliation_preview(db, account_id, statement_end_date, ending_balance)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/{account_id}", response_model=ReconciliationRead, status_code=201)
def reconcile_account(
    account_id: int,
    body: ReconciliationCreate,
    db: Session = Depends(get_db),
) -> ReconciliationRead:
    if not db.get(Account, account_id):
        raise HTTPException(404, "Account not found")
    rec = create_reconciliation(db, account_id, body)
    return rec
