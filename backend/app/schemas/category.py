from __future__ import annotations
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.category import CategoryType


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    category_type: CategoryType
    parent_id: Optional[int]


class CategoryCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    category_type: CategoryType
    parent_id: Optional[int] = None


class CategoryPatch(BaseModel):
    name: Optional[str] = None
    category_type: Optional[CategoryType] = None
