from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class PlaidItem(Base, TimestampMixin):
    __tablename__ = "plaid_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    institution_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_holdings_sync_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    transactions_cursor: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_investment_sync_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    accounts: Mapped[List["PlaidAccount"]] = relationship(back_populates="plaid_item")


class PlaidAccount(Base, TimestampMixin):
    __tablename__ = "plaid_account"

    id: Mapped[int] = mapped_column(primary_key=True)
    plaid_item_id: Mapped[int] = mapped_column(ForeignKey("plaid_item.id"), nullable=False)
    plaid_account_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    official_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    mask: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    balance_current: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    plaid_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    plaid_subtype: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("account.id"), nullable=True)

    plaid_item: Mapped["PlaidItem"] = relationship(back_populates="accounts")
    ledger_account: Mapped[Optional["Account"]] = relationship(back_populates="plaid_account")
