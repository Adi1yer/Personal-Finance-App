"""Google Drive backup OAuth + backup/restore APIs."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_profile, get_db
from app.config import get_settings
from app.models.profile import Profile
from app.services import google_drive_pending as pending
from app.services.google_drive_backup import (
    GoogleDriveError,
    connection_status,
    create_backup,
    disconnect,
    list_backups,
    restore_backup,
    save_tokens,
)
from app.services.browser_open import open_in_browser
from app.services.google_drive_oauth import build_auth_url, exchange_code, make_pkce

router = APIRouter(prefix="/google-drive", tags=["google-drive"])
browser_router = APIRouter(prefix="/google-drive", tags=["google-drive-browser"])


class ExchangeRequest(BaseModel):
    code: str
    state: str


class RestoreRequest(BaseModel):
    file_id: str


@router.get("/status")
def status(
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    settings = get_settings()
    out = connection_status(db)
    out["configured"] = settings.google_drive_configured
    out["redirect_uri"] = settings.google_oauth_redirect_uri
    return out


@router.post("/connect")
def connect(
    profile: Profile = Depends(get_current_profile),
) -> dict[str, str]:
    settings = get_settings()
    if not settings.google_drive_configured:
        raise HTTPException(
            400,
            "Google Drive is not configured. Add GOOGLE_OAUTH_CLIENT_ID / "
            "GOOGLE_OAUTH_CLIENT_SECRET / ENCRYPTION_KEY to .env",
        )
    verifier, challenge = make_pkce()
    state = pending.create_pending(profile.id, verifier)
    auth_url = build_auth_url(state=state, code_challenge=challenge)
    # Open from the API process — frontend window.open after await is popup-blocked.
    browser = open_in_browser(auth_url)
    return {"auth_url": auth_url, "state": state, "browser": browser}


@router.post("/disconnect")
def disconnect_drive(db: Session = Depends(get_db)) -> dict[str, str]:
    disconnect(db)
    return {"status": "disconnected"}


@router.get("/backups")
def get_backups(db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return {"backups": list_backups(db)}
    except GoogleDriveError as e:
        raise HTTPException(400, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/backup")
def post_backup(
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return create_backup(db, profile.id)
    except GoogleDriveError as e:
        raise HTTPException(400, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/restore")
def post_restore(
    body: RestoreRequest,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return restore_backup(db, profile.id, body.file_id)
    except GoogleDriveError as e:
        raise HTTPException(400, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@browser_router.post("/browser/exchange")
def browser_exchange(body: ExchangeRequest) -> dict[str, Any]:
    """Unauthenticated localhost callback exchange (profile bound via OAuth state)."""
    settings = get_settings()
    if not settings.google_drive_configured:
        raise HTTPException(400, "Google Drive is not configured")

    session = pending.pop_pending(body.state)
    if not session:
        raise HTTPException(400, "Invalid or expired OAuth state. Try Connect again.")

    try:
        tokens = exchange_code(body.code, code_verifier=session.code_verifier)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    from app.db.profile_db import get_profile_session_factory

    factory = get_profile_session_factory(session.profile_id)
    db = factory()
    try:
        result = save_tokens(db, tokens)
    except GoogleDriveError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        db.close()

    return {"status": "connected", **result}
