"""Institution-specific transaction heuristics (generic + Chase)."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Protocol

# Ignore tiny cash-sweep parking (interest → sweep). Real ACH contributions are larger.
MIN_CONTRIBUTION = Decimal("100")

_CONTRIBUTION_SUBTYPES = frozenset({"contribution", "match", "deposit"})
_WITHDRAW_RE = re.compile(r"WITHDR", re.IGNORECASE)

# Chase-specific (and similar brokerages that use deposit-sweep ACH mapping).
_CHASE_EXPLICIT_RE = re.compile(
    r"BANKLINK|ACH\s+PULL|IRA:C\d|\bCONTRIBUTION\b|\bCONTRIB\b",
    re.IGNORECASE,
)
_CHASE_SWEEP_DEPOSIT_RE = re.compile(
    r"DEPOSIT\s+SWEEP.*\bDEPOSIT\b|\bINTRA-DAY\s+DEPOSIT\b",
    re.IGNORECASE,
)
_CHASE_HINT_RE = re.compile(r"\bCHASE\b|\bJPMORGAN\b|\bBANKLINK\b|\bIRA:C\d", re.I)


class ContributionDetector(Protocol):
    def looks_like_contribution(
        self,
        *,
        payee: str,
        memo: str | None,
        investment_subtype: str | None,
        amount: Decimal | None,
        is_cash_equivalent: bool | None,
        raw: dict[str, Any] | None,
    ) -> bool: ...


class GenericContributionDetector:
    """Plaid-standard contribution / match / deposit subtypes only."""

    def looks_like_contribution(
        self,
        *,
        payee: str,
        memo: str | None,
        investment_subtype: str | None,
        amount: Decimal | None,
        is_cash_equivalent: bool | None,
        raw: dict[str, Any] | None,
    ) -> bool:
        subtype = (investment_subtype or "").strip().lower()
        return subtype in _CONTRIBUTION_SUBTYPES


class ChaseContributionDetector:
    """Chase maps ACH IRA/brokerage deposits to cash-sweep buys in Plaid."""

    def looks_like_contribution(
        self,
        *,
        payee: str,
        memo: str | None,
        investment_subtype: str | None,
        amount: Decimal | None,
        is_cash_equivalent: bool | None,
        raw: dict[str, Any] | None,
    ) -> bool:
        subtype = (investment_subtype or "").strip().lower()
        if subtype in _CONTRIBUTION_SUBTYPES:
            return True

        hay = f"{payee or ''} {memo or ''}".strip()
        if not hay:
            return False
        if _WITHDRAW_RE.search(hay):
            return False
        if _CHASE_EXPLICIT_RE.search(hay):
            return True

        cash_eq = is_cash_equivalent
        if cash_eq is None and raw is not None:
            security_id = raw.get("security_id")
            securities = raw.get("_securities") or {}
            if security_id and security_id in securities:
                cash_eq = bool(securities[security_id].get("is_cash_equivalent"))

        if amount is not None and abs(Decimal(str(amount))) < MIN_CONTRIBUTION:
            return False

        if _CHASE_SWEEP_DEPOSIT_RE.search(hay):
            return True

        if cash_eq and subtype == "buy" and re.search(r"\bDEPOSIT\b", hay, re.I):
            return True

        return False


_GENERIC = GenericContributionDetector()
_CHASE = ChaseContributionDetector()


def resolve_contribution_detector(
    *,
    payee: str = "",
    memo: str | None = None,
    institution_name: str | None = None,
) -> ContributionDetector:
    """Pick Chase rules when the institution or payee looks like Chase; else generic."""
    blob = f"{institution_name or ''} {payee or ''} {memo or ''}"
    if _CHASE_HINT_RE.search(blob):
        return _CHASE
    return _GENERIC


def looks_like_external_contribution(
    *,
    payee: str,
    memo: str | None = None,
    investment_subtype: str | None = None,
    amount: Decimal | None = None,
    is_cash_equivalent: bool | None = None,
    raw: dict[str, Any] | None = None,
    institution_name: str | None = None,
) -> bool:
    detector = resolve_contribution_detector(
        payee=payee, memo=memo, institution_name=institution_name
    )
    return detector.looks_like_contribution(
        payee=payee,
        memo=memo,
        investment_subtype=investment_subtype,
        amount=amount,
        is_cash_equivalent=is_cash_equivalent,
        raw=raw,
    )
