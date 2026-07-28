"""Persist manual card payment mask → account mappings."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.card_payment_mapping import CardPaymentMapping
from app.models.plaid import PlaidAccount
from app.services.card_payments import resolve_card_account_from_payment


def get_card_for_payment(db: Session, payee: str) -> dict | None:
    from app.models.account import Account

    match = resolve_card_account_from_payment(db, payee)
    if match:
        pa = db.query(PlaidAccount).filter(PlaidAccount.account_id == match.id).first()
        return {
            "account_id": match.id,
            "account_name": match.name,
            "mask": pa.mask if pa else None,
            "source": "auto",
        }
    import re

    m = re.search(r"ending in (\d{4})", payee, re.I)
    if not m:
        return None
    mask = m.group(1)
    mapping = db.query(CardPaymentMapping).filter(CardPaymentMapping.mask == mask).first()
    if not mapping:
        return {"mask": mask, "account_id": None, "account_name": None, "source": "unmapped"}
    acc = db.get(Account, mapping.account_id)
    return {
        "account_id": mapping.account_id,
        "account_name": acc.name if acc else None,
        "mask": mask,
        "source": "manual",
    }


def set_card_mapping(db: Session, mask: str, account_id: int) -> dict:
    row = db.query(CardPaymentMapping).filter(CardPaymentMapping.mask == mask).first()
    if row:
        row.account_id = account_id
    else:
        db.add(CardPaymentMapping(mask=mask, account_id=account_id))
    db.commit()
    return {"mask": mask, "account_id": account_id}
