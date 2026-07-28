from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AdvisorActionLog(Base, TimestampMixin):
    __tablename__ = "advisor_action_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    args_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
