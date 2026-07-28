from __future__ import annotations

import enum
from datetime import date
from decimal import Decimal

from typing import Optional

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class StagingStatus(str, enum.Enum):
    pending = "pending"
    posted = "posted"
    skipped = "skipped"


class ImportStaging(Base, TimestampMixin):
    __tablename__ = "import_staging"

    id: Mapped[int] = mapped_column(primary_key=True)
    plaid_account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("plaid_account.id"), nullable=True
    )
    external_id: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    txn_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    payee: Mapped[str] = mapped_column(String(256), default="")
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[StagingStatus] = mapped_column(
        Enum(StagingStatus), default=StagingStatus.pending
    )
