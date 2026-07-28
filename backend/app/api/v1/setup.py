"""First-run / BYO connections setup (localhost only)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services import app_config

router = APIRouter(prefix="/setup", tags=["setup"])


def _require_localhost(request: Request) -> None:
    host = (request.client.host if request.client else "") or ""
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(403, "Setup is only available from localhost")


class SetupPatch(BaseModel):
    encryption_key: Optional[str] = None
    generate_encryption_key: bool = False
    plaid_client_id: Optional[str] = None
    plaid_secret: Optional[str] = None
    plaid_env: Optional[str] = None
    plaid_enabled: Optional[bool] = None
    plaid_redirect_uri: Optional[str] = None
    google_oauth_client_id: Optional[str] = None
    google_oauth_client_secret: Optional[str] = None
    google_oauth_redirect_uri: Optional[str] = None


@router.get("/status")
def get_setup_status(request: Request) -> dict[str, Any]:
    _require_localhost(request)
    return app_config.setup_status()


@router.post("/ensure-encryption-key")
def post_ensure_encryption_key(request: Request) -> dict[str, Any]:
    _require_localhost(request)
    key = app_config.ensure_encryption_key()
    return {"encryption_key_set": True, "generated": True, "hint": "Key stored in data/app_config.json"}


@router.post("")
def post_setup(request: Request, body: SetupPatch) -> dict[str, Any]:
    _require_localhost(request)
    patch: dict[str, Any] = {}
    if body.generate_encryption_key:
        app_config.ensure_encryption_key()
    data = body.model_dump(exclude_unset=True, exclude={"generate_encryption_key"})
    for key, value in data.items():
        if value is not None:
            patch[key] = value
    if patch:
        app_config.save_app_config(patch)
    return app_config.setup_status()
