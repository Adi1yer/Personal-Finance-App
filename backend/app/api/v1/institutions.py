from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.institution import Institution
from app.schemas.institution import InstitutionCreate, InstitutionRead
from app.services.slug import slugify

router = APIRouter(prefix="/institutions", tags=["institutions"])


@router.get("", response_model=list[InstitutionRead])
def list_institutions(db: Session = Depends(get_db)) -> list[Institution]:
    return db.query(Institution).order_by(Institution.name).all()


@router.post("", response_model=InstitutionRead, status_code=201)
def create_institution(body: InstitutionCreate, db: Session = Depends(get_db)) -> Institution:
    slug = body.slug or slugify(body.name)
    if db.query(Institution).filter(Institution.slug == slug).first():
        raise HTTPException(400, "Institution already exists")
    inst = Institution(name=body.name, slug=slug)
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst
