from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.account import Account, AccountType
from app.models.transaction import Transaction
from app.services.categorization import matching_rules, normalize_rule_patterns, resolve_category_id
from app.services.category_assignment import apply_category_to_transaction
from app.services.payee_normalization import infer_direction


def _txn_amount_for_direction(db: Session, txn: Transaction) -> Decimal | None:
    for entry in txn.entries:
        acc = db.get(Account, entry.account_id)
        if acc and acc.account_type in (AccountType.asset, AccountType.liability):
            return Decimal(str(entry.amount))
    return None


def _transaction_direction(db: Session, txn: Transaction) -> str:
    amount = _txn_amount_for_direction(db, txn)
    return infer_direction(txn.payee, txn.memo, amount=amount)


def _txn_account_subtype(db: Session, txn: Transaction) -> str | None:
    for entry in txn.entries:
        acc = db.get(Account, entry.account_id)
        if acc and acc.account_type in (AccountType.asset, AccountType.liability):
            return acc.subtype.value
    return None


def recategorize_transactions(db: Session, *, from_staging: bool = True) -> dict[str, int]:
    updated = skipped = cleared = 0
    txns = db.query(Transaction).filter(Transaction.voided_at.is_(None)).all()
    staging_by_ext = {}
    if from_staging:
        from app.models.import_staging import ImportStaging

        for row in db.query(ImportStaging).all():
            staging_by_ext[row.external_id] = row

    for txn in txns:
        raw_json = None
        investment_subtype = txn.investment_subtype
        if txn.external_id and txn.external_id in staging_by_ext:
            raw_json = staging_by_ext[txn.external_id].raw_json
            if not investment_subtype:
                try:
                    data = json.loads(raw_json or "{}")
                    investment_subtype = data.get("subtype")
                except json.JSONDecodeError:
                    pass

        direction = _transaction_direction(db, txn)
        account_subtype = _txn_account_subtype(db, txn)
        matched = matching_rules(
            db,
            payee=txn.payee,
            memo=txn.memo or "",
            direction=direction,
            account_subtype=account_subtype,
        )
        distinct = {rule.category_id for rule in matched}

        if len(distinct) > 1:
            before = {e.id: e.category_id for e in txn.entries}
            apply_category_to_transaction(db, txn.entries[0], None)
            if {e.id: e.category_id for e in txn.entries} != before:
                cleared += 1
            continue

        amount = _txn_amount_for_direction(db, txn)
        category_id = resolve_category_id(
            db,
            payee=txn.payee,
            memo=txn.memo,
            raw_json=raw_json,
            investment_subtype=investment_subtype,
            investment_type=txn.investment_type,
            security_name=txn.security_name,
            amount=amount,
            account_subtype=account_subtype,
            is_transfer=txn.is_transfer,
        )
        if not category_id:
            skipped += 1
            continue

        before = {e.id: e.category_id for e in txn.entries}
        apply_category_to_transaction(db, txn.entries[0], category_id)
        if {e.id: e.category_id for e in txn.entries} != before:
            updated += 1
        else:
            skipped += 1

    db.commit()
    return {"updated": updated, "skipped": skipped, "cleared_ambiguous": cleared}


def repair_category_rules(db: Session) -> dict[str, int]:
    """Normalize legacy rule patterns and recategorize ambiguous matches."""
    patterns_updated = normalize_rule_patterns(db)
    result = recategorize_transactions(db, from_staging=True)
    return {"patterns_updated": patterns_updated, **result}


def repair_transaction_recognition(db: Session) -> dict[str, int]:
    """Normalize category rules to canonical keys and re-run categorization."""
    patterns_updated = normalize_rule_patterns(db)
    result = recategorize_transactions(db, from_staging=True)
    return {
        "rules_rewritten": patterns_updated,
        "recategorized": result.get("updated", 0),
        "skipped": result.get("skipped", 0),
        "cleared_ambiguous": result.get("cleared_ambiguous", 0),
    }
