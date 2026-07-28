from __future__ import annotations

import enum

from typing import Optional

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class CategoryType(str, enum.Enum):
    income = "income"
    expense = "expense"


class Category(Base, TimestampMixin):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    category_type: Mapped[CategoryType] = mapped_column(Enum(CategoryType), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("category.id"), nullable=True)

    parent: Mapped[Optional["Category"]] = relationship(remote_side="Category.id")
