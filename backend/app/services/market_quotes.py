"""Fetch live equity prices for investment account valuation."""

from __future__ import annotations

import logging
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

_YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {"User-Agent": "personal-finance-app/1.0"}


def fetch_live_quote(symbol: str, *, client: httpx.Client | None = None) -> Decimal | None:
    sym = symbol.strip().upper()
    if not sym:
        return None
    try:
        if client is None:
            with httpx.Client(timeout=10.0, trust_env=False) as owned:
                return _fetch_quote_with_client(owned, sym)
        return _fetch_quote_with_client(client, sym)
    except Exception:
        logger.warning("Live quote failed for %s", sym, exc_info=True)
        return None


def _fetch_quote_with_client(client: httpx.Client, symbol: str) -> Decimal | None:
    response = client.get(
        _YAHOO_CHART.format(symbol=symbol),
        params={"interval": "1d", "range": "1d"},
        headers=_HEADERS,
    )
    response.raise_for_status()
    result = response.json().get("chart", {}).get("result") or []
    if not result:
        return None
    price = result[0].get("meta", {}).get("regularMarketPrice")
    if price is None:
        return None
    return Decimal(str(price)).quantize(Decimal("0.0001"))


def fetch_live_quotes(symbols: list[str]) -> dict[str, Decimal]:
    unique = sorted({s.strip().upper() for s in symbols if s and s.strip()})
    quotes: dict[str, Decimal] = {}
    if not unique:
        return quotes
    with httpx.Client(timeout=10.0, trust_env=False) as client:
        for sym in unique:
            price = fetch_live_quote(sym, client=client)
            if price is not None:
                quotes[sym] = price
    return quotes
