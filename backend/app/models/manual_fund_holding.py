from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ManualFundHolding(Base, TimestampMixin):
    __tablename__ = "manual_fund_holding"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    allocation_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)

    account: Mapped["Account"] = relationship()
