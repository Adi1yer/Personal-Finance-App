from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.cash_flow_mapping import CashFlowMapping
from app.models.category import Category, CategoryType
from app.models.category_rule import CategoryRule
from app.models.entry import Entry
from app.services.seed import PROTECTED_CATEGORY_SLUGS


def update_category(
    db: Session,
    category_id: int,
    *,
    name: str | None = None,
    category_type: CategoryType | None = None,
) -> Category:
    cat = db.get(Category, category_id)
    if not cat:
        raise HTTPException(404, "Category not found")
    if name is not None:
        trimmed = name.strip()
        if not trimmed:
            raise HTTPException(400, "Category name is required")
        cat.name = trimmed
    if category_type is not None:
        cat.category_type = category_type
    db.commit()
    db.refresh(cat)
    return cat


def delete_category(db: Session, category_id: int) -> None:
    cat = db.get(Category, category_id)
    if not cat:
        raise HTTPException(404, "Category not found")
    if cat.slug in PROTECTED_CATEGORY_SLUGS:
        raise HTTPException(400, "Built-in categories cannot be deleted")

    db.query(Entry).filter(Entry.category_id == category_id).update(
        {Entry.category_id: None}, synchronize_session=False
    )
    db.query(CategoryRule).filter(CategoryRule.category_id == category_id).delete(
        synchronize_session=False
    )
    db.query(CashFlowMapping).filter(CashFlowMapping.category_id == category_id).delete(
        synchronize_session=False
    )
    db.delete(cat)
    db.commit()
