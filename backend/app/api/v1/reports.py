from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.reports import (
    BalanceSheetReport,
    CashFlowReport,
    IncomeStatementReport,
    MonthlyMetrics,
    NetWorthHistoryReport,
    QuarterlyMetrics,
)
from app.services.reports import (
    balance_sheet,
    cash_flow_statement,
    income_statement,
    monthly_metrics,
    net_worth_history,
    quarter_date_range,
    quarterly_metrics,
    reports_readiness,
)
from app.services.reports.export import export_quarter_package

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/readiness")
def get_reports_readiness(
    as_of: Optional[date] = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    return reports_readiness(db, as_of)


@router.get("/package")
def get_report_package(
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    format: str = Query("csv", pattern="^(csv|pdf)$"),
    db: Session = Depends(get_db),
) -> Response:
    readiness = reports_readiness(db)
    if not readiness["ready"]:
        raise HTTPException(
            400,
            detail={
                "message": "Update 401(k) and HSA balances before generating statements",
                "stale_accounts": readiness["stale_accounts"],
            },
        )
    fmt = "csv" if format == "csv" else "pdf"
    content_type, filename, body = export_quarter_package(db, year, quarter, fmt)
    return Response(
        content=body,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/balance-sheet", response_model=BalanceSheetReport)
def get_balance_sheet(
    as_of: date = Query(..., description="Balance sheet date YYYY-MM-DD"),
    db: Session = Depends(get_db),
) -> BalanceSheetReport:
    return balance_sheet(db, as_of)


@router.get("/income-statement", response_model=IncomeStatementReport)
def get_income_statement(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
) -> IncomeStatementReport:
    return income_statement(db, start, end)


@router.get("/cash-flow", response_model=CashFlowReport)
def get_cash_flow(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
) -> CashFlowReport:
    return cash_flow_statement(db, start, end)


@router.get("/metrics/monthly", response_model=MonthlyMetrics)
def get_monthly_metrics(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
) -> MonthlyMetrics:
    return monthly_metrics(db, year, month)


@router.get("/metrics/quarterly", response_model=QuarterlyMetrics)
def get_quarterly_metrics(
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    db: Session = Depends(get_db),
) -> QuarterlyMetrics:
    return quarterly_metrics(db, year, quarter)


@router.get("/net-worth/history", response_model=NetWorthHistoryReport)
def get_net_worth_history(db: Session = Depends(get_db)) -> NetWorthHistoryReport:
    return net_worth_history(db)


@router.get("/tax-export/{year}")
def get_tax_export(year: int, db: Session = Depends(get_db)) -> dict:
    from app.services.tax_export import build_tax_export

    return build_tax_export(db, year)


@router.get("/investment-reconcile")
def get_investment_reconcile(db: Session = Depends(get_db)) -> list[dict]:
    from app.services.investment_reconcile import reconcile_positions

    return reconcile_positions(db)
