from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.annual_goals import get_annual_goals_progress
from app.services.projection_engine import run_projection
from app.services.profile_settings import update_settings

router = APIRouter(prefix="/goals", tags=["goals"])


class ProjectionRequest(BaseModel):
    horizon_years: Optional[int] = None
    stock_appreciation_pct: Optional[float] = None
    dividend_growth_pct: Optional[float] = None
    per_ticker_overrides: Optional[dict[str, dict[str, float]]] = None


class AssumptionsPatch(BaseModel):
    projection_horizon_years: Optional[int] = None
    stock_appreciation_pct: Optional[float] = None
    dividend_growth_pct: Optional[float] = None
    per_ticker_overrides: Optional[dict[str, dict[str, float]]] = None
    investing_pct_of_income: Optional[float] = None
    safety_net_pct_of_income: Optional[float] = None
    safety_net_account_id: Optional[int] = None
    annual_income_override: Optional[float] = None


@router.get("/progress")
def goals_progress(db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_annual_goals_progress(db)


@router.get("/projections")
def get_projections(
    db: Session = Depends(get_db),
    horizon_years: int = Query(20, ge=1, le=40),
    stock_appreciation_pct: float = Query(7.0),
    dividend_growth_pct: float = Query(3.0),
) -> dict[str, Any]:
    return run_projection(
        db,
        horizon_years=horizon_years,
        stock_appreciation_pct=stock_appreciation_pct,
        dividend_growth_pct=dividend_growth_pct,
    )


@router.post("/projections")
def post_projections(body: ProjectionRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    return run_projection(
        db,
        horizon_years=body.horizon_years,
        stock_appreciation_pct=body.stock_appreciation_pct,
        dividend_growth_pct=body.dividend_growth_pct,
        per_ticker_overrides=body.per_ticker_overrides,
    )


@router.patch("/assumptions")
def patch_assumptions(body: AssumptionsPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    patch = body.model_dump(exclude_none=True)
    update_settings(db, patch)
    return {"updated": list(patch.keys())}
