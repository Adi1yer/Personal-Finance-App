from __future__ import annotations

import enum
from datetime import date, datetime

from decimal import Decimal
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class TransactionSource(str, enum.Enum):
    manual = "manual"
    plaid = "plaid"
    import_csv = "import_csv"


class Transaction(Base, TimestampMixin):
    __tablename__ = "transaction"

    id: Mapped[int] = mapped_column(primary_key=True)
    txn_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payee: Mapped[str] = mapped_column(String(256), default="")
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[TransactionSource] = mapped_column(
        default=TransactionSource.manual
    )
    external_id: Mapped[Optional[str]] = mapped_column(String(256), unique=True, nullable=True)
    is_transfer: Mapped[bool] = mapped_column(Boolean, default=False)
    voided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    investment_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    investment_subtype: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    security_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)

    entries: Mapped[List["Entry"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan"
    )
