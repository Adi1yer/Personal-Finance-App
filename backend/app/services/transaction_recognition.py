from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from app.services.categorization import is_card_payment, parse_plaid_raw
from app.services.payee_normalization import (
    AmountDirection,
    parse_venmo,
    parse_zelle,
    strip_trailing_id,
    transaction_direction,
)

_CARD_MASK_RE = re.compile(r"ending in (\d{4})", re.I)
_STORE_NUM_RE = re.compile(r"\s+#\d+\b", re.I)
_STORE_WORD_RE = re.compile(r"\s+STORE\s+\d+\b", re.I)
_DIV_ON_RE = re.compile(r"\bDIV\s+ON\b", re.I)
_DIVIDEND_RE = re.compile(r"\bDIVIDEND\b", re.I)
_REINVEST_RE = re.compile(r"\bREINVEST\s*@", re.I)
_SWEEP_RE = re.compile(r"\b(?:CHASE|IRA)\s+DEPOSIT\s+SWEEP\b", re.I)
_SWEEP_DEPOSIT_RE = re.compile(r"\bINTRA-DAY\s+DEPOSIT\b|\bDEPOSIT\s+SWEEP.*\bDEPOSIT\b", re.I)
_WITHDRAW_RE = re.compile(r"WITHDR", re.I)
_BANKLINK_RE = re.compile(r"BANKLINK|ACH\s+PULL|IRA:C\d", re.I)
_COMMISSION_RE = re.compile(r"\bCOMMISSION\b", re.I)

_CARD_PAYMENT_MARKERS = (
    "PAYMENT THANK YOU",
    "PAYMENT RECEIVED",
    "AUTOMATIC PAYMENT",
    "MOBILE PAYMENT",
    "ONLINE PAYMENT",
    "AUTOPAY",
    "AUTO-PAY",
)
_CARD_REFUND_MARKERS = (
    "REFUND",
    "RETURN",
    "REVERSAL",
    "CREDIT ADJUSTMENT",
    "STATEMENT CREDIT",
    "CASH BACK",
    "CASHBACK",
    "REWARD",
    "REWARDS",
    "PURCHASE STATEMENT CREDIT",
)
_CARD_FEE_MARKERS = (
    "INTEREST CHARGE",
    "FINANCE CHARGE",
    "ANNUAL FEE",
    "LATE FEE",
    "MEMBERSHIP FEE",
)
_PAYROLL_MARKERS = ("PAYROLL", "DIRECT DEP", "SALARY", "DIR DEP")

MERCHANT_PREFIX_MAP: dict[str, str] = {
    "AMZN MKTP": "Amazon",
    "AMAZON.COM": "Amazon",
    "AMAZON PRIME": "Amazon",
    "WHOLEFDS": "Whole Foods",
    "WHOLE FOODS": "Whole Foods",
    "STARBUCKS": "Starbucks",
    "TRADER JOE": "Trader Joe's",
    "COSTCO WHSE": "Costco",
    "WAL-MART": "Walmart",
    "WALMART": "Walmart",
}

KNOWN_TICKER_FROM_NAME: dict[str, str] = {
    "BLACKROCK SCIENCE": "BST",
    "BLACKROCK SCIENCE & TECHNOLOGY": "BST",
    "TESLA": "TSLA",
    "HAPN": "HAPN",
}

KNOWN_TICKERS = ("TSLA", "BST", "HAPN", "AAPL", "MSFT", "GOOGL", "AMZN")


@dataclass(frozen=True)
class RecognizedTransaction:
    canonical_key: str
    activity_label: str | None
    direction: AmountDirection
    family: str | None
    ticker: str | None
    suggested_category_slug: str | None
    is_internal_transfer: bool = False


def conflict_group_key(
    recognized: RecognizedTransaction,
    *,
    payee: str = "",
    memo: str | None = None,
) -> str:
    """Group key for spotting inconsistent categories among similar transactions."""
    from app.services.payee_normalization import detect_provider, parse_zelle

    provider = detect_provider(payee, memo)
    if provider == "venmo":
        # All Venmo rows share one bucket — balance transfers and payments alike.
        return "venmo"
    if provider == "zelle":
        zelle = parse_zelle(payee) or (parse_zelle(memo) if memo else None)
        if zelle:
            return zelle.canonical
    if recognized.family == "zelle":
        return recognized.canonical_key
    return recognized.canonical_key


def _upper(text: str) -> str:
    return text.upper()


def _title_merchant(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name.strip())
    if not cleaned:
        return ""
    if cleaned.isupper() and len(cleaned) > 3:
        return cleaned.title()
    return cleaned


def extract_ticker(
    *,
    payee: str = "",
    security_name: str | None = None,
    memo: str | None = None,
) -> str | None:
    if security_name:
        name = security_name.strip()
        if re.match(r"^[A-Z]{1,6}$", name):
            return name
        for key, ticker in KNOWN_TICKER_FROM_NAME.items():
            if key in name.upper():
                return ticker
        m = re.search(r"\b([A-Z]{1,5})\b", name)
        if m:
            return m.group(1)
        words = name.split()
        if words:
            first = words[0].upper()
            if len(first) <= 5 and first.isalpha():
                return first

    haystack = f"{payee} {memo or ''}".upper()
    for ticker in KNOWN_TICKERS:
        if ticker in haystack:
            return ticker
    for key, ticker in KNOWN_TICKER_FROM_NAME.items():
        if key in haystack:
            return ticker
    return None


def _merchant_from_raw(raw: dict[str, Any]) -> str | None:
    counterparty = raw.get("counterparty") or {}
    for key in ("name", "merchant_name"):
        val = raw.get(key) or counterparty.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return None


def normalize_merchant(payee: str, raw: dict[str, Any] | None = None) -> str:
    from_raw = _merchant_from_raw(raw) if raw else None
    base = (from_raw or payee or "").strip()
    base = _STORE_NUM_RE.sub("", base)
    base = _STORE_WORD_RE.sub("", base)
    for prefix in ("SQ *", "TST *", "SP *", "PAYPAL *"):
        if base.upper().startswith(prefix):
            base = base[len(prefix) :].strip()
            break
    upper = base.upper()
    for prefix, canonical in MERCHANT_PREFIX_MAP.items():
        if upper.startswith(prefix) or prefix in upper:
            return canonical
    base = strip_trailing_id(base)
    return _title_merchant(base) or payee.strip()


def _direction_from_inputs(
    *,
    charge: Decimal | None,
    payment: Decimal | None,
    amount: Decimal | None,
    zelle_direction: str | None = None,
) -> AmountDirection:
    direction = transaction_direction(charge, payment)
    if direction != "none":
        return direction
    if amount is not None:
        if amount < 0:
            return "outflow"
        if amount > 0:
            return "inflow"
    if zelle_direction == "to":
        return "outflow"
    if zelle_direction == "from":
        return "inflow"
    return "none"


def _parse_investment(
    payee: str,
    memo: str | None,
    *,
    security_name: str | None,
    investment_subtype: str | None,
    amount: Decimal | None,
    direction: AmountDirection,
) -> RecognizedTransaction | None:
    haystack = f"{payee} {memo or ''} {security_name or ''}"
    ticker = extract_ticker(payee=payee, security_name=security_name, memo=memo)

    if _BANKLINK_RE.search(haystack) or (
        _SWEEP_DEPOSIT_RE.search(haystack)
        and not _WITHDRAW_RE.search(haystack)
        and amount is not None
        and abs(amount) >= Decimal("100")
    ):
        return RecognizedTransaction(
            canonical_key="Investment contribution",
            activity_label="Contribution",
            direction="inflow",
            family="contribution",
            ticker=None,
            suggested_category_slug="investment_contribution",
            is_internal_transfer=False,
        )

    if _SWEEP_RE.search(haystack):
        return RecognizedTransaction(
            canonical_key="Chase deposit sweep",
            activity_label="Cash sweep",
            direction="none",
            family="sweep",
            ticker=None,
            suggested_category_slug=None,
            is_internal_transfer=True,
        )

    if _REINVEST_RE.search(haystack) or (
        investment_subtype and "reinvest" in investment_subtype.lower()
    ):
        label = f"Reinvest {ticker}".strip() if ticker else "Reinvest"
        key = f"{ticker} reinvest".strip() if ticker else "Reinvest"
        return RecognizedTransaction(
            canonical_key=key,
            activity_label=label,
            direction="outflow",
            family="reinvest",
            ticker=ticker,
            suggested_category_slug="interest_dividends",
        )

    if _DIV_ON_RE.search(haystack) or _DIVIDEND_RE.search(haystack) or (
        investment_subtype and investment_subtype.lower() in ("dividend", "interest")
    ):
        label = f"Dividend {ticker}".strip() if ticker else "Dividend"
        key = f"{ticker} dividend".strip() if ticker else "Dividend"
        return RecognizedTransaction(
            canonical_key=key,
            activity_label=label,
            direction="inflow",
            family="dividend",
            ticker=ticker,
            suggested_category_slug="interest_dividends",
        )

    if _COMMISSION_RE.search(haystack):
        return RecognizedTransaction(
            canonical_key="Commission",
            activity_label="Commission",
            direction="outflow",
            family="fee",
            ticker=ticker,
            suggested_category_slug=None,
        )

    subtype = (investment_subtype or "").lower()
    if subtype in ("buy", "fee") or direction == "outflow":
        if ticker:
            return RecognizedTransaction(
                canonical_key=f"{ticker} purchase",
                activity_label=f"Purchase {ticker}",
                direction="outflow",
                family="purchase",
                ticker=ticker,
                suggested_category_slug=None,
            )
    if subtype == "sell" or (direction == "inflow" and ticker):
        return RecognizedTransaction(
            canonical_key=f"{ticker} sale" if ticker else "Sale",
            activity_label=f"Sale {ticker}".strip() if ticker else "Sale",
            direction="inflow",
            family="sale",
            ticker=ticker,
            suggested_category_slug=None,
        )

    return None


def _parse_card_payment(
    payee: str,
    raw: dict[str, Any],
    amount: float,
    *,
    on_credit_card: bool,
) -> RecognizedTransaction | None:
    label_upper = _upper(payee)
    is_payment = is_card_payment(raw, amount, payee=payee)
    if not is_payment:
        if not any(m in label_upper for m in _CARD_PAYMENT_MARKERS):
            if not ("PAYMENT TO" in label_upper and "CARD" in label_upper):
                return None

    mask_match = _CARD_MASK_RE.search(payee)
    if mask_match:
        canonical = f"Card payment ••••{mask_match.group(1)}"
    else:
        canonical = "Card payment"

    return RecognizedTransaction(
        canonical_key=canonical,
        activity_label="Payment",
        direction="inflow" if on_credit_card else "outflow",
        family="card_payment",
        ticker=None,
        suggested_category_slug=None,
        is_internal_transfer=True,
    )


def _parse_credit_card(
    payee: str,
    raw: dict[str, Any] | None,
    *,
    direction: AmountDirection,
    amount: float,
) -> RecognizedTransaction | None:
    label_upper = _upper(payee)
    raw = raw or {}

    payment = _parse_card_payment(payee, raw, amount, on_credit_card=True)
    if payment:
        return payment

    if any(m in label_upper for m in _CARD_REFUND_MARKERS):
        merchant = normalize_merchant(payee, raw)
        if "STATEMENT CREDIT" in label_upper:
            activity = "Statement credit"
        elif "CASH BACK" in label_upper or "CASHBACK" in label_upper or "REWARD" in label_upper:
            activity = "Cash back"
        else:
            activity = f"Refund {merchant}".strip()
        return RecognizedTransaction(
            canonical_key=merchant or activity,
            activity_label=activity,
            direction="inflow",
            family="card_refund",
            ticker=None,
            suggested_category_slug="other_income",
        )

    if any(m in label_upper for m in _CARD_FEE_MARKERS):
        if "ANNUAL" in label_upper or "MEMBERSHIP" in label_upper:
            activity = "Annual fee"
        elif "LATE" in label_upper:
            activity = "Late fee"
        else:
            activity = "Interest charge"
        return RecognizedTransaction(
            canonical_key=activity,
            activity_label=activity,
            direction="outflow",
            family="card_fee",
            ticker=None,
            suggested_category_slug="utilities",
        )

    # Register inflow (correctly posted credit) or Plaid money-in (amount < 0 in raw).
    plaid_money_in = bool(raw.get("amount") is not None and amount < 0)
    if direction == "inflow" or plaid_money_in:
        merchant = normalize_merchant(payee, raw)
        return RecognizedTransaction(
            canonical_key=merchant,
            activity_label=f"Credit {merchant}".strip(),
            direction="inflow",
            family="card_refund",
            ticker=None,
            suggested_category_slug="other_income",
        )

    if direction == "outflow" or amount > 0:
        merchant = normalize_merchant(payee, raw)
        return RecognizedTransaction(
            canonical_key=merchant,
            activity_label=f"Purchase {merchant}".strip(),
            direction="outflow",
            family="card_purchase",
            ticker=None,
            suggested_category_slug=None,
        )

    return None


def _parse_p2p(payee: str, memo: str | None, direction: AmountDirection) -> RecognizedTransaction | None:
    zelle = parse_zelle(payee) or (parse_zelle(memo) if memo else None)
    if zelle:
        return RecognizedTransaction(
            canonical_key=zelle.canonical,
            activity_label=zelle.canonical,
            direction="outflow" if zelle.direction == "to" else "inflow",
            family="zelle",
            ticker=None,
            suggested_category_slug=None,
        )

    venmo = parse_venmo(payee) or (parse_venmo(memo) if memo else None)
    if venmo:
        return RecognizedTransaction(
            canonical_key=venmo,
            activity_label=f"Venmo {venmo}",
            direction=direction if direction != "none" else "outflow",
            family="venmo",
            ticker=None,
            suggested_category_slug=None,
        )

    haystack = f"{payee} {memo or ''}".upper()
    if "APPLE CASH" in haystack and "BALANCE TRANSFER" in haystack:
        return RecognizedTransaction(
            canonical_key="Apple Cash balance transfer",
            activity_label="Apple Cash balance transfer",
            direction=direction if direction != "none" else "outflow",
            family="apple_cash",
            ticker=None,
            suggested_category_slug=None,
        )

    return None


def _parse_payroll(payee: str, memo: str | None) -> RecognizedTransaction | None:
    haystack = f"{payee} {memo or ''}".upper()
    if any(m in haystack for m in _PAYROLL_MARKERS):
        return RecognizedTransaction(
            canonical_key=payee.strip(),
            activity_label="Payroll",
            direction="inflow",
            family="payroll",
            ticker=None,
            suggested_category_slug="salary",
        )
    return None


def _parse_merchant_fallback(
    payee: str,
    raw: dict[str, Any] | None,
    direction: AmountDirection,
) -> RecognizedTransaction:
    merchant = normalize_merchant(payee, raw)
    activity = merchant
    if direction == "outflow":
        activity = f"Purchase {merchant}".strip() if merchant else None
    elif direction == "inflow":
        activity = f"Deposit {merchant}".strip() if merchant else None
    return RecognizedTransaction(
        canonical_key=merchant or payee.strip(),
        activity_label=activity,
        direction=direction,
        family="merchant",
        ticker=None,
        suggested_category_slug=None,
    )


def recognize_transaction(
    *,
    payee: str,
    memo: str | None = None,
    amount: Decimal | None = None,
    account_subtype: str | None = None,
    raw_json: str | None = None,
    investment_type: str | None = None,
    investment_subtype: str | None = None,
    security_name: str | None = None,
    is_transfer: bool = False,
    charge: Decimal | None = None,
    payment: Decimal | None = None,
) -> RecognizedTransaction:
    raw: dict[str, Any] = parse_plaid_raw(raw_json) if raw_json else {}
    plaid_amount = float(raw.get("amount", float(amount or 0)))
    subtype = (account_subtype or "").lower()
    is_investment = subtype in ("brokerage", "retirement", "hsa") or bool(
        investment_type or investment_subtype
    )

    zelle = parse_zelle(payee) or (parse_zelle(memo) if memo else None)
    direction = _direction_from_inputs(
        charge=charge,
        payment=payment,
        amount=amount,
        zelle_direction=zelle.direction if zelle else None,
    )

    if is_transfer:
        return RecognizedTransaction(
            canonical_key=payee.strip(),
            activity_label="Transfer",
            direction="none",
            family="transfer",
            ticker=None,
            suggested_category_slug=None,
            is_internal_transfer=True,
        )

    p2p = _parse_p2p(payee, memo, direction)
    if p2p:
        return p2p

    if is_investment:
        inv = _parse_investment(
            payee,
            memo,
            security_name=security_name,
            investment_subtype=investment_subtype,
            amount=amount,
            direction=direction,
        )
        if inv:
            return inv

    if subtype == "credit_card":
        card = _parse_credit_card(payee, raw, direction=direction, amount=plaid_amount)
        if card:
            return card

    if subtype == "checking" or not subtype:
        card_pay = _parse_card_payment(payee, raw, plaid_amount, on_credit_card=False)
        if card_pay:
            return card_pay

    payroll = _parse_payroll(payee, memo)
    if payroll:
        return payroll

    return _parse_merchant_fallback(payee, raw, direction)


def canonical_key_from_text(
    payee: str,
    memo: str | None = None,
    *,
    account_subtype: str | None = None,
) -> str:
    return recognize_transaction(
        payee=payee,
        memo=memo,
        account_subtype=account_subtype,
    ).canonical_key
