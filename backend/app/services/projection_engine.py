"""Project portfolio value and dividend income over time."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.account import Account, AccountSubtype
from app.models.manual_fund_holding import ManualFundHolding
from app.services.dividend_inference import infer_dividends_by_ticker
from app.services.holdings import list_holdings, portfolio_value
from app.services.profile_settings import get_all_settings


def _pct(value: float | Decimal) -> Decimal:
    return Decimal(str(value)) / Decimal("100")


def _holdings_by_account(db: Session) -> dict[int, list[dict[str, Any]]]:
    accounts = (
        db.query(Account)
        .filter(
            Account.is_active.is_(True),
            Account.subtype.in_(
                [
                    AccountSubtype.brokerage,
                    AccountSubtype.retirement,
                    AccountSubtype.hsa,
                ]
            ),
        )
        .all()
    )
    out: dict[int, list[dict[str, Any]]] = {}
    for acc in accounts:
        if acc.subtype in (AccountSubtype.retirement, AccountSubtype.hsa):
            funds = db.query(ManualFundHolding).filter(ManualFundHolding.account_id == acc.id).all()
            if funds:
                _, port = portfolio_value(db, acc.id)
                port_val = port or Decimal("0")
                rows = []
                for f in funds:
                    weight = Decimal(str(f.allocation_pct or 0)) / Decimal("100")
                    if f.quantity:
                        rows.append(
                            {
                                "ticker": f.ticker.upper(),
                                "market_value": str(Decimal(str(f.quantity))),
                                "annual_dividend": "0",
                            }
                        )
                    else:
                        mv = (port_val * weight).quantize(Decimal("0.01"))
                        rows.append(
                            {
                                "ticker": f.ticker.upper(),
                                "market_value": str(mv),
                                "annual_dividend": "0",
                            }
                        )
                out[acc.id] = rows
                continue
        holdings = list_holdings(db, acc.id)
        rows = []
        for h in holdings:
            mv = h.market_value or Decimal("0")
            rows.append(
                {
                    "ticker": h.ticker.upper(),
                    "market_value": str(mv),
                    "annual_dividend": "0",
                }
            )
        out[acc.id] = rows
    return out


def run_projection(
    db: Session,
    *,
    horizon_years: int | None = None,
    stock_appreciation_pct: float | None = None,
    dividend_growth_pct: float | None = None,
    per_ticker_overrides: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    settings = get_all_settings(db)
    years = horizon_years or int(settings.get("projection_horizon_years", 20))
    appreciation = _pct(
        stock_appreciation_pct if stock_appreciation_pct is not None else settings["stock_appreciation_pct"]
    )
    div_growth = _pct(
        dividend_growth_pct if dividend_growth_pct is not None else settings["dividend_growth_pct"]
    )
    overrides = per_ticker_overrides or settings.get("per_ticker_overrides") or {}
    dividend_map = infer_dividends_by_ticker(db)

    holdings = _holdings_by_account(db)
    series: list[dict[str, Any]] = []
    accounts_out: list[dict[str, Any]] = []

    total_value = Decimal("0")
    total_annual_div = Decimal("0")
    for account_id, positions in holdings.items():
        acc = db.get(Account, account_id)
        acct_value = Decimal("0")
        acct_div = Decimal("0")
        for pos in positions:
            ticker = pos["ticker"]
            mv = Decimal(pos["market_value"])
            div_info = dividend_map.get(ticker, {})
            annual_div = Decimal(div_info.get("annualized", "0"))
            ticker_ov = overrides.get(ticker, {})
            appr = _pct(ticker_ov.get("appreciation_pct", float(appreciation * 100)))
            dg = _pct(ticker_ov.get("dividend_growth_pct", float(div_growth * 100)))
            acct_value += mv
            acct_div += annual_div
        total_value += acct_value
        total_annual_div += acct_div
        accounts_out.append(
            {
                "account_id": account_id,
                "account_name": acc.name if acc else "",
                "current_value": str(acct_value.quantize(Decimal("0.01"))),
                "current_annual_dividend": str(acct_div.quantize(Decimal("0.01"))),
            }
        )

    value = total_value
    annual_div = total_annual_div
    for year in range(years + 1):
        series.append(
            {
                "year": year,
                "portfolio_value": str(value.quantize(Decimal("0.01"))),
                "annual_dividend_income": str(annual_div.quantize(Decimal("0.01"))),
                "monthly_dividend_income": str((annual_div / 12).quantize(Decimal("0.01"))),
            }
        )
        if year < years:
            value *= Decimal("1") + appreciation
            annual_div *= Decimal("1") + div_growth

    final = series[-1] if series else {}
    return {
        "horizon_years": years,
        "assumptions": {
            "stock_appreciation_pct": float(appreciation * 100),
            "dividend_growth_pct": float(div_growth * 100),
        },
        "current": {
            "portfolio_value": str(total_value.quantize(Decimal("0.01"))),
            "annual_dividend_income": str(total_annual_div.quantize(Decimal("0.01"))),
        },
        "projected_final": final,
        "series": series,
        "accounts": accounts_out,
    }
