from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class CategoryRule(Base, TimestampMixin):
    __tablename__ = "category_rule"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_field: Mapped[str] = mapped_column(String(16), nullable=False)  # payee | memo
    pattern: Mapped[str] = mapped_column(String(256), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    amount_direction: Mapped[str] = mapped_column(String(8), default="any")  # any | outflow | inflow

    category: Mapped["Category"] = relationship()
