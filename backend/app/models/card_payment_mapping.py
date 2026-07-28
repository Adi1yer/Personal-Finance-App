from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class CardPaymentMapping(Base, TimestampMixin):
    __tablename__ = "card_payment_mapping"

    id: Mapped[int] = mapped_column(primary_key=True)
    mask: Mapped[str] = mapped_column(String(4), nullable=False, unique=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), nullable=False)

    account: Mapped["Account"] = relationship()
