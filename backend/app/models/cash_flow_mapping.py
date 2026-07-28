from __future__ import annotations

import enum

from typing import Optional

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CashFlowCategory(str, enum.Enum):
    operating = "operating"
    investing = "investing"
    financing = "financing"


class CashFlowMapping(Base, TimestampMixin):
    __tablename__ = "cash_flow_mapping"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("category.id"), nullable=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("account.id"), nullable=True)
    cash_flow_type: Mapped[CashFlowCategory] = mapped_column(Enum(CashFlowCategory))
    label: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
