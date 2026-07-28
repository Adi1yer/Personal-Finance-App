from decimal import Decimal
from unittest.mock import patch

from app.services.market_quotes import fetch_live_quote, fetch_live_quotes


def test_fetch_live_quotes_empty():
    assert fetch_live_quotes([]) == {}


@patch("app.services.market_quotes.fetch_live_quote")
def test_fetch_live_quotes_collects_results(mock_quote):
    mock_quote.side_effect = lambda sym, client=None: {
        "TSLA": Decimal("406.55"),
        "BST": Decimal("48.21"),
    }.get(sym)

    quotes = fetch_live_quotes(["TSLA", "BST", "TSLA"])
    assert quotes == {"BST": Decimal("48.21"), "TSLA": Decimal("406.55")}


@patch("app.services.market_quotes._fetch_quote_with_client")
def test_fetch_live_quote_parses_yahoo_response(mock_fetch):
    mock_fetch.return_value = Decimal("406.5500")
    assert fetch_live_quote("tsla") == Decimal("406.5500")
