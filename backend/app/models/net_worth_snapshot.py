from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class NetWorthSnapshot(Base, TimestampMixin):
    __tablename__ = "net_worth_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    by_group_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
