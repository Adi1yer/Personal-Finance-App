from __future__ import annotations

from decimal import Decimal
from typing import Literal

from app.services.transaction_recognition import RecognizedTransaction

CashDirection = Literal["outflow", "inflow", "none"]

REGISTER_COLUMN_LABELS: dict[str, tuple[str, str, str]] = {
    "checking": ("Withdrawal", "Deposit", "Balance"),
    "credit_card": ("Charge", "Payment", "Balance owed"),
    "brokerage": ("Purchase", "Sale & income", "Cash balance"),
    "retirement": ("Contribution", "Distribution & income", "Cash balance"),
    "hsa": ("Purchase", "Distribution & income", "Cash balance"),
    "other": ("Withdrawal", "Deposit", "Balance"),
}


def cash_direction_from_amount(amount: Decimal) -> CashDirection:
    if amount < 0:
        return "outflow"
    if amount > 0:
        return "inflow"
    return "none"


def activity_label_from_recognition(recognized: RecognizedTransaction) -> str | None:
    return recognized.activity_label


def register_column_labels(subtype: str) -> tuple[str, str, str]:
    return REGISTER_COLUMN_LABELS.get(subtype, ("Withdrawal", "Deposit", "Balance"))
