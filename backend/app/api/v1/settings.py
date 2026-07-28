from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.email_service import check_smtp, send_email, smtp_configured
from app.services.hedge_fund_import import hedge_env_available, import_hedge_fund_settings
from app.services.ollama_client import (
    health_check,
    model_is_available,
    ollama_base_url,
    ollama_model,
)
from app.services.profile_settings import get_all_settings, update_settings

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    settings: dict[str, Any]
    ollama: dict[str, Any]
    smtp: dict[str, Any] = {}


class SettingsPatch(BaseModel):
    settings: dict[str, Any]


class TestEmailRequest(BaseModel):
    to_addr: Optional[str] = None


def _ollama_status(settings: dict[str, Any]) -> dict[str, Any]:
    ollama = health_check(ollama_base_url(settings))
    configured = ollama_model(settings)
    ollama["configured_model"] = configured
    ollama["model_loaded"] = model_is_available(configured, ollama.get("models") or [])
    return ollama


def _smtp_status(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "configured": smtp_configured(settings),
        "host": settings.get("smtp_host") or "",
        "from": settings.get("smtp_from") or settings.get("smtp_user") or "",
        "digest_email": settings.get("digest_email") or "",
        "hedge_env_available": hedge_env_available(),
    }


@router.get("", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)) -> SettingsResponse:
    settings = get_all_settings(db)
    return SettingsResponse(
        settings=settings,
        ollama=_ollama_status(settings),
        smtp=_smtp_status(settings),
    )


@router.patch("", response_model=SettingsResponse)
def patch_settings(body: SettingsPatch, db: Session = Depends(get_db)) -> SettingsResponse:
    settings = update_settings(db, body.settings)
    return SettingsResponse(
        settings=settings,
        ollama=_ollama_status(settings),
        smtp=_smtp_status(settings),
    )


@router.post("/import-hedge-fund")
def post_import_hedge(db: Session = Depends(get_db), overwrite: bool = False) -> dict[str, Any]:
    """Copy SMTP credentials from ~/ai-hedge-fund-production/.env into this profile."""
    result = import_hedge_fund_settings(db, overwrite=overwrite)
    settings = get_all_settings(db)
    result["smtp"] = _smtp_status(settings)
    result["ollama"] = _ollama_status(settings)
    return result


@router.post("/check-smtp")
def post_check_smtp(db: Session = Depends(get_db)) -> dict[str, Any]:
    return check_smtp(get_all_settings(db))


@router.post("/test-email")
def post_test_email(body: TestEmailRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    settings = get_all_settings(db)
    to_addr = body.to_addr or settings.get("digest_email") or ""
    if not to_addr:
        raise HTTPException(400, "No recipient email configured")
    try:
        return send_email(
            settings,
            to_addr=to_addr,
            subject="Personal Finance test email",
            body_text="SMTP is working — same Gmail STARTTLS setup as your hedge-fund project.",
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"SMTP send failed: {e}") from e
