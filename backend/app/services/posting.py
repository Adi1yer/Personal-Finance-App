from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.account import Account, AccountSubtype, AccountType
from app.models.entry import Entry
from app.models.transaction import Transaction, TransactionSource
from app.schemas.transaction import EntryLine, TransactionCreate


class PostingError(Exception):
    pass


def _validate_balanced(entries: list[EntryLine]) -> None:
    total = sum(e.amount for e in entries)
    if total != 0:
        raise PostingError(f"Entries must sum to zero; got {total}")


def create_transaction(
    db: Session,
    data: TransactionCreate,
    *,
    is_transfer: bool = False,
    source: TransactionSource = TransactionSource.manual,
) -> Transaction:
    _validate_balanced(data.entries)
    if data.external_id:
        existing = (
            db.query(Transaction)
            .filter(Transaction.external_id == data.external_id)
            .first()
        )
        if existing:
            if existing.voided_at is None:
                return existing
            existing.external_id = None
            db.flush()

    txn = Transaction(
        txn_date=data.txn_date,
        payee=data.payee,
        memo=data.memo,
        external_id=data.external_id,
        is_transfer=is_transfer,
        source=source,
    )
    db.add(txn)
    db.flush()

    for line in data.entries:
        db.add(
            Entry(
                transaction_id=txn.id,
                account_id=line.account_id,
                category_id=line.category_id,
                amount=line.amount,
                entry_date=data.txn_date,
            )
        )
    db.commit()
    db.refresh(txn)
    return txn


def create_transfer(
    db: Session,
    txn_date: date,
    from_account_id: int,
    to_account_id: int,
    amount: Decimal,
    memo: str | None = None,
) -> Transaction:
    if from_account_id == to_account_id:
        raise PostingError("Transfer accounts must differ")
    amt = Decimal(str(amount))
    return create_transaction(
        db,
        TransactionCreate(
            txn_date=txn_date,
            payee="Transfer",
            memo=memo,
            entries=[
                EntryLine(account_id=from_account_id, amount=-amt),
                EntryLine(account_id=to_account_id, amount=amt),
            ],
        ),
        is_transfer=True,
    )


def _get_expense_account(db: Session) -> Account:
    acc = (
        db.query(Account)
        .filter(Account.account_type == AccountType.expense, Account.slug == "uncategorized_expense")
        .first()
    )
    if not acc:
        raise PostingError("Uncategorized expense account missing; run seed-accounts")
    return acc


def create_card_purchase(
    db: Session,
    txn_date: date,
    card_account_id: int,
    category_id: int,
    amount: Decimal,
    payee: str = "",
    memo: str | None = None,
    expense_account_id: int | None = None,
) -> Transaction:
    card = db.get(Account, card_account_id)
    if not card or card.subtype != AccountSubtype.credit_card:
        raise PostingError("card_account_id must be a credit card account")
    expense_id = expense_account_id or _get_expense_account(db).id
    amt = Decimal(str(amount))
    return create_transaction(
        db,
        TransactionCreate(
            txn_date=txn_date,
            payee=payee,
            memo=memo,
            entries=[
                EntryLine(account_id=expense_id, amount=amt, category_id=category_id),
                EntryLine(account_id=card_account_id, amount=-amt),
            ],
        ),
    )


def create_card_payment(
    db: Session,
    txn_date: date,
    checking_account_id: int,
    card_account_id: int,
    amount: Decimal,
    memo: str | None = None,
) -> Transaction:
    checking = db.get(Account, checking_account_id)
    card = db.get(Account, card_account_id)
    if not checking or checking.subtype != AccountSubtype.checking:
        raise PostingError("checking_account_id must be a checking account")
    if not card or card.subtype != AccountSubtype.credit_card:
        raise PostingError("card_account_id must be a credit card account")
    amt = Decimal(str(amount))
    return create_transaction(
        db,
        TransactionCreate(
            txn_date=txn_date,
            payee="Card payment",
            memo=memo,
            entries=[
                EntryLine(account_id=card_account_id, amount=amt),
                EntryLine(account_id=checking_account_id, amount=-amt),
            ],
        ),
        is_transfer=False,
    )
