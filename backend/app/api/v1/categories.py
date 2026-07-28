from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryPatch, CategoryRead
from app.services.categories import delete_category, update_category
from app.services.slug import unique_category_slug

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead])
def list_categories(db: Session = Depends(get_db)) -> list[Category]:
    return db.query(Category).order_by(Category.name).all()


@router.post("", response_model=CategoryRead, status_code=201)
def create_category(body: CategoryCreate, db: Session = Depends(get_db)) -> Category:
    slug = body.slug or unique_category_slug(db, body.name)
    if db.query(Category).filter(Category.slug == slug).first():
        raise HTTPException(400, "Category slug already exists")
    cat = Category(
        name=body.name.strip(),
        slug=slug,
        category_type=body.category_type,
        parent_id=body.parent_id,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.patch("/{category_id}", response_model=CategoryRead)
def patch_category(
    category_id: int,
    body: CategoryPatch,
    db: Session = Depends(get_db),
) -> Category:
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "No updates provided")
    return update_category(
        db,
        category_id,
        name=updates.get("name"),
        category_type=updates.get("category_type"),
    )


@router.delete("/{category_id}", status_code=204)
def remove_category(category_id: int, db: Session = Depends(get_db)) -> Response:
    delete_category(db, category_id)
    return Response(status_code=204)
