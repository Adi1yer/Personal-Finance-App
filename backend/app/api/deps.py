from __future__ import annotations

from collections.abc import Generator
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.profile_db import get_profile_db as _profile_db_gen
from app.db.registry import get_registry_session_factory
from app.models.profile import Profile
from app.services.auth import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_registry_db() -> Generator[Session, None, None]:
    factory = get_registry_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


def get_current_profile(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Profile:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Not signed in")
    payload = decode_access_token(credentials.credentials)
    profile_id = payload.get("sub")
    if not profile_id:
        raise HTTPException(401, "Invalid session")

    db = get_registry_session_factory()()
    try:
        profile = db.get(Profile, profile_id)
        if not profile:
            raise HTTPException(401, "Profile not found")
        return profile
    finally:
        db.close()


def get_db(
    profile: Profile = Depends(get_current_profile),
) -> Generator[Session, None, None]:
    yield from _profile_db_gen(profile.id)
