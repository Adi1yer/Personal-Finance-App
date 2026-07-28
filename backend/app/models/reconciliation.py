from __future__ import annotations

from datetime import date
from decimal import Decimal

from typing import List

from sqlalchemy import Date, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Reconciliation(Base, TimestampMixin):
    __tablename__ = "reconciliation"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), nullable=False)
    statement_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    ending_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    entries: Mapped[List["ReconciliationEntry"]] = relationship(
        back_populates="reconciliation", cascade="all, delete-orphan"
    )


class ReconciliationEntry(Base, TimestampMixin):
    __tablename__ = "reconciliation_entry"

    id: Mapped[int] = mapped_column(primary_key=True)
    reconciliation_id: Mapped[int] = mapped_column(
        ForeignKey("reconciliation.id"), nullable=False
    )
    entry_id: Mapped[int] = mapped_column(ForeignKey("entry.id"), nullable=False)

    reconciliation: Mapped["Reconciliation"] = relationship(back_populates="entries")
