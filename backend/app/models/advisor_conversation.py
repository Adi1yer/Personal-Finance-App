from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class AdvisorConversation(Base, TimestampMixin):
    __tablename__ = "advisor_conversation"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="New chat")

    messages: Mapped[list["AdvisorChatMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AdvisorChatMessage.id",
    )
