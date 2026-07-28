from __future__ import annotations
from typing import Optional

from pydantic import BaseModel, ConfigDict


class InstitutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str


class InstitutionCreate(BaseModel):
    name: str
    slug: Optional[str] = None
