from __future__ import annotations

from datetime import date
from decimal import Decimal

from typing import Optional

from sqlalchemy import Date, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AccountMark(Base, TimestampMixin):
    __tablename__ = "account_mark"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    market_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(nullable=True)
