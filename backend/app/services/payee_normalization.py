from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

AmountDirection = Literal["any", "outflow", "inflow", "none"]

ZELLE_PREFIX_RE = re.compile(r"(?i)^zelle payment (to|from)\s+")
TRAILING_ID_RE = re.compile(r"\s+[A-Za-z0-9]{8,}$")
VENMO_PREFIX_RE = re.compile(r"(?i)^venmo\s*\*?\s*")


@dataclass(frozen=True)
class ZelleInfo:
    direction: str  # to | from
    counterparty: str
    canonical: str


def strip_trailing_id(text: str) -> str:
    return TRAILING_ID_RE.sub("", text.strip()).strip()


def parse_zelle(payee: str) -> ZelleInfo | None:
    s = payee.strip()
    match = ZELLE_PREFIX_RE.match(s)
    if not match:
        return None
    direction = match.group(1).lower()
    rest = strip_trailing_id(s[match.end() :])
    counterparty = rest.strip()
    if not counterparty:
        return None
    canonical = f"Zelle payment {direction} {counterparty.upper()}"
    return ZelleInfo(direction=direction, counterparty=counterparty, canonical=canonical)


def parse_venmo(payee: str) -> str | None:
    s = payee.strip()
    if "venmo" not in s.lower():
        return None
    normalized = VENMO_PREFIX_RE.sub("", s)
    normalized = strip_trailing_id(normalized)
    return normalized.strip() or s.strip()


def canonical_match_key(payee: str, memo: str | None = None, *, account_subtype: str | None = None) -> str:
    from app.services.transaction_recognition import canonical_key_from_text

    return canonical_key_from_text(payee, memo, account_subtype=account_subtype)


def transaction_direction(
    charge: Decimal | None,
    payment: Decimal | None,
) -> AmountDirection:
    has_charge = charge is not None and charge > 0
    has_payment = payment is not None and payment > 0
    if has_charge and not has_payment:
        return "outflow"
    if has_payment and not has_charge:
        return "inflow"
    return "none"


def direction_from_amount(amount: Decimal) -> AmountDirection:
    if amount < 0:
        return "outflow"
    if amount > 0:
        return "inflow"
    return "none"


def infer_direction(
    payee: str,
    memo: str | None = None,
    *,
    charge: Decimal | None = None,
    payment: Decimal | None = None,
    amount: Decimal | None = None,
) -> AmountDirection:
    direction = transaction_direction(charge, payment)
    if direction != "none":
        return direction
    if amount is not None:
        direction = direction_from_amount(amount)
        if direction != "none":
            return direction
    zelle = parse_zelle(payee) or (parse_zelle(memo) if memo else None)
    if zelle:
        return "outflow" if zelle.direction == "to" else "inflow"
    return "none"


def detect_provider(payee: str, memo: str | None = None) -> str | None:
    haystack = f"{payee} {memo or ''}".lower()
    if parse_zelle(payee) or (memo and parse_zelle(memo)):
        return "zelle"
    if "venmo" in haystack:
        return "venmo"
    return None
