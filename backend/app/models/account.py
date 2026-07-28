from __future__ import annotations

import enum
from typing import List, Optional

from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class AccountType(str, enum.Enum):
    asset = "asset"
    liability = "liability"
    income = "income"
    expense = "expense"
    equity = "equity"


class AccountSubtype(str, enum.Enum):
    checking = "checking"
    credit_card = "credit_card"
    brokerage = "brokerage"
    retirement = "retirement"
    hsa = "hsa"
    other = "other"


class SyncSource(str, enum.Enum):
    manual = "manual"
    plaid = "plaid"


class Account(Base, TimestampMixin):
    __tablename__ = "account"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[Optional[int]] = mapped_column(ForeignKey("institution.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    account_type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False)
    subtype: Mapped[AccountSubtype] = mapped_column(
        Enum(AccountSubtype), default=AccountSubtype.other
    )
    sync_source: Mapped[SyncSource] = mapped_column(
        Enum(SyncSource), default=SyncSource.manual
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    tracking_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    institution: Mapped[Optional["Institution"]] = relationship(back_populates="accounts")
    entries: Mapped[List["Entry"]] = relationship(back_populates="account")
    plaid_account: Mapped[Optional["PlaidAccount"]] = relationship(
        back_populates="ledger_account", uselist=False
    )
