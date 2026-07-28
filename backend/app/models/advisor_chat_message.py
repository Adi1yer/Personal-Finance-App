from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class AdvisorChatMessage(Base, TimestampMixin):
    __tablename__ = "advisor_chat_message"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("advisor_conversation.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    conversation: Mapped[Optional["AdvisorConversation"]] = relationship(
        back_populates="messages"
    )
