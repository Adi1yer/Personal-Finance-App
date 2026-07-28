from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models.entry import Entry
from app.models.transaction import Transaction
from app.schemas.register import EntryPatch
from app.schemas.transaction import EntryRead
from app.services.category_assignment import apply_category_to_transaction

router = APIRouter(prefix="/entries", tags=["entries"])


@router.patch("/{entry_id}", response_model=EntryRead)
def patch_entry(
    entry_id: int,
    body: EntryPatch,
    db: Session = Depends(get_db),
) -> Entry:
    entry = (
        db.query(Entry)
        .options(joinedload(Entry.transaction).joinedload(Transaction.entries))
        .filter(Entry.id == entry_id)
        .first()
    )
    if not entry:
        raise HTTPException(404, "Entry not found")
    updates = body.model_dump(exclude_unset=True)
    if "category_id" in updates:
        apply_category_to_transaction(db, entry, updates["category_id"])
    if "is_cleared" in updates:
        entry.is_cleared = updates["is_cleared"]
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/card-payment/resolve")
def resolve_card_payment(payee: str, db: Session = Depends(get_db)) -> dict:
    from app.services.card_payment_mappings import get_card_for_payment

    result = get_card_for_payment(db, payee)
    if not result:
        return {"mapped": False}
    return {"mapped": result.get("account_id") is not None, **result}


@router.post("/card-payment/map")
def map_card_payment(body: dict, db: Session = Depends(get_db)) -> dict:
    from app.services.card_payment_mappings import set_card_mapping

    return set_card_mapping(db, body["mask"], int(body["account_id"]))
