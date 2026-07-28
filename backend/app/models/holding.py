from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Holding(Base, TimestampMixin):
    __tablename__ = "holding"
    __table_args__ = (UniqueConstraint("account_id", "ticker", name="uq_holding_account_ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    security_name: Mapped[str] = mapped_column(String(256), default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    cost_basis_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    market_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    as_of_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    account: Mapped["Account"] = relationship()
