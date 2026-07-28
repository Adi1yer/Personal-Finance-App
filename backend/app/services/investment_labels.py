from __future__ import annotations

from app.services.register_labels import (  # noqa: F401
    REGISTER_COLUMN_LABELS,
    cash_direction_from_amount,
    register_column_labels,
)

INVESTMENT_COLUMN_LABELS = {
    k: v for k, v in REGISTER_COLUMN_LABELS.items() if k in ("brokerage", "retirement", "hsa")
}
