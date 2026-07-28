from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.account import Account, AccountType
from app.models.category_rule import CategoryRule
from app.models.entry import Entry
from app.models.transaction import Transaction
from app.services.categorization import matching_rules
from app.services.payee_normalization import infer_direction


def apply_category_to_transaction(
    db: Session, entry: Entry, category_id: int | None
) -> None:
    txn = entry.transaction
    if not txn:
        return
    if category_id is None:
        for sibling in txn.entries:
            sibling.category_id = None
        return

    has_classification_entry = False
    for sibling in txn.entries:
        acc = db.get(Account, sibling.account_id)
        if acc and acc.account_type in (AccountType.expense, AccountType.income):
            sibling.category_id = category_id
            has_classification_entry = True
        else:
            sibling.category_id = None

    if has_classification_entry:
        return

    for sibling in txn.entries:
        acc = db.get(Account, sibling.account_id)
        if acc and acc.account_type in (AccountType.asset, AccountType.liability):
            sibling.category_id = category_id
        else:
            sibling.category_id = None


def _entry_categories(txn: Transaction) -> dict[int, int | None]:
    return {e.id: e.category_id for e in txn.entries}


def _transaction_direction_for_rule(db: Session, txn: Transaction) -> str:
    for entry in txn.entries:
        acc = db.get(Account, entry.account_id)
        if not acc:
            continue
        if acc.account_type in (AccountType.asset, AccountType.liability):
            amount = Decimal(str(entry.amount))
            direction = infer_direction(txn.payee, txn.memo, amount=amount)
            if direction != "none":
                return direction
    return infer_direction(txn.payee, txn.memo)


def apply_category_rule_to_matching(db: Session, rule: CategoryRule) -> int:
    updated = 0
    txns = db.query(Transaction).filter(Transaction.voided_at.is_(None)).all()
    for txn in txns:
        direction = _transaction_direction_for_rule(db, txn)
        matched = matching_rules(
            db, payee=txn.payee, memo=txn.memo or "", direction=direction
        )
        if len(matched) != 1 or matched[0].id != rule.id:
            continue
        before = _entry_categories(txn)
        apply_category_to_transaction(db, txn.entries[0], rule.category_id)
        if _entry_categories(txn) != before:
            updated += 1
    if updated:
        db.commit()
    return updated
