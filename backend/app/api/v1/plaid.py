from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.api.deps import get_current_profile, get_db
from app.db.profile_db import get_profile_session_factory
from app.models.profile import Profile
from app.schemas.plaid import (
    LinkTokenRequest,
    LinkTokenResponse,
    PlaidAccountRead,
    PlaidBrowserLinkResponse,
    PlaidBrowserSessionResponse,
    PlaidExchangeResponse,
    PlaidMapRequest,
    PlaidResetResponse,
    PlaidStatusResponse,
    PlaidSyncResponse,
    PublicTokenExchange,
    SyncHealthResponse,
)
from app.services import plaid_pending, plaid_sync
from app.services.browser_open import open_plaid_link
from app.services.sync_health import build_health_summary, store_sync_health

router = APIRouter(prefix="/plaid", tags=["plaid"])
# Safari/Chrome bank link — no JWT (browser has no app session); localhost-only.
browser_router = APIRouter(prefix="/plaid", tags=["plaid"])


def _require_plaid() -> None:
    settings = get_settings()
    if not settings.plaid_enabled or not settings.plaid_configured:
        raise HTTPException(
            503,
            "Plaid is disabled. Set PLAID_ENABLED=true and add credentials to .env",
        )


def _require_localhost(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Local only")


def _browser_link_url(redirect_uri: str | None = None) -> str:
    resolved = plaid_sync.effective_redirect_uri(redirect_uri)
    parsed = urlparse(resolved)
    return f"{parsed.scheme}://{parsed.netloc}/plaid-link.html"


@router.get("/status", response_model=PlaidStatusResponse)
def get_status(db: Session = Depends(get_db)) -> PlaidStatusResponse:
    return PlaidStatusResponse(**plaid_sync.plaid_status(db))


@router.get("/accounts", response_model=list[PlaidAccountRead])
def list_plaid_accounts(db: Session = Depends(get_db)) -> list[PlaidAccountRead]:
    return [PlaidAccountRead(**row) for row in plaid_sync.list_plaid_accounts(db)]


@router.post("/link-token", response_model=LinkTokenResponse)
def link_token(
    body: Optional[LinkTokenRequest] = Body(default=None),
    profile: Profile = Depends(get_current_profile),
) -> LinkTokenResponse:
    _require_plaid()
    redirect_uri = body.redirect_uri if body else None
    resolved = plaid_sync.effective_redirect_uri(redirect_uri)
    try:
        token = plaid_sync.create_link_token(
            redirect_uri, client_user_id=str(profile.id)
        )
        return LinkTokenResponse(link_token=token, redirect_uri=resolved)
    except Exception as e:
        msg = str(e)
        if "redirect" in msg.lower() or "oauth" in msg.lower():
            hint = (
                " Add the redirect URI to Plaid Dashboard → Team Settings → API → "
                "Allowed redirect URIs"
            )
            if resolved:
                hint += f" (e.g. {resolved})"
            raise HTTPException(502, f"Plaid error: {msg}.{hint}") from e
        raise HTTPException(502, f"Plaid error: {e}") from e


@router.post("/begin-browser-link", response_model=PlaidBrowserLinkResponse)
def begin_browser_link(
    request: Request,
    body: Optional[LinkTokenRequest] = Body(default=None),
    profile: Profile = Depends(get_current_profile),
) -> PlaidBrowserLinkResponse:
    """Open Plaid Link in the system browser (required for OAuth banks like Chase)."""
    _require_plaid()
    redirect_uri = body.redirect_uri if body else None
    try:
        token = plaid_sync.create_link_token(
            redirect_uri, client_user_id=str(profile.id)
        )
    except Exception as e:
        msg = str(e)
        resolved = plaid_sync.effective_redirect_uri(redirect_uri)
        if "redirect" in msg.lower() or "oauth" in msg.lower():
            hint = (
                " Add the redirect URI to Plaid Dashboard → Team Settings → API → "
                "Allowed redirect URIs"
            )
            if resolved:
                hint += f" (e.g. {resolved})"
            raise HTTPException(502, f"Plaid error: {msg}.{hint}") from e
        raise HTTPException(502, f"Plaid error: {e}") from e

    plaid_pending.save_browser_link(profile.id, token)
    url = _browser_link_url(redirect_uri)
    browser = open_plaid_link(url)
    return PlaidBrowserLinkResponse(opened=True, url=url, browser=browser)


@browser_router.get("/browser-session", response_model=PlaidBrowserSessionResponse)
def browser_session(request: Request) -> PlaidBrowserSessionResponse:
    _require_localhost(request)
    session = plaid_pending.get_browser_link()
    if not session:
        raise HTTPException(404, "No pending bank connection. Click Connect bank in the app.")
    return PlaidBrowserSessionResponse(link_token=session.link_token)


@browser_router.post("/browser-exchange", response_model=PlaidExchangeResponse)
def browser_exchange(
    body: PublicTokenExchange,
    request: Request,
) -> PlaidExchangeResponse:
    _require_localhost(request)
    _require_plaid()
    session = plaid_pending.get_browser_link()
    if not session:
        raise HTTPException(400, "No pending bank connection")

    factory = get_profile_session_factory(session.profile_id)
    db = factory()
    try:
        item = plaid_sync.exchange_public_token(db, body.public_token)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(502, f"Plaid error: {e}") from e
    finally:
        db.close()

    plaid_pending.clear_browser_link(session.profile_id)
    return PlaidExchangeResponse(
        item_id=item.item_id,
        institution_name=item.institution_name,
    )


@router.post("/exchange", response_model=PlaidExchangeResponse)
def exchange_token(
    body: PublicTokenExchange,
    db: Session = Depends(get_db),
) -> PlaidExchangeResponse:
    _require_plaid()
    try:
        item = plaid_sync.exchange_public_token(db, body.public_token)
        return PlaidExchangeResponse(
            item_id=item.item_id,
            institution_name=item.institution_name,
        )
    except Exception as e:
        raise HTTPException(502, f"Plaid error: {e}") from e


@router.patch("/accounts/{plaid_account_id}/map", response_model=PlaidAccountRead)
def map_account(
    plaid_account_id: int,
    body: PlaidMapRequest,
    db: Session = Depends(get_db),
) -> PlaidAccountRead:
    _require_plaid()
    try:
        pa = plaid_sync.map_plaid_account(
            db,
            plaid_account_id,
            ledger_account_id=body.ledger_account_id,
            create_ledger_account=body.create_ledger_account,
            ledger_account_name=body.ledger_account_name,
            account_type=body.account_type,
            subtype=body.subtype,
        )
        rows = plaid_sync.list_plaid_accounts(db)
        row = next((r for r in rows if r["id"] == pa.id), None)
        if not row:
            raise HTTPException(500, "Mapping failed")
        return PlaidAccountRead(**row)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, str(e)) from e


@router.post("/reset", response_model=PlaidResetResponse)
def reset_plaid(db: Session = Depends(get_db)) -> PlaidResetResponse:
    """Remove Plaid bank connections and imported transactions. Keeps ledger accounts."""
    from app.services.plaid_cleanup import reset_plaid_data

    try:
        return PlaidResetResponse(**reset_plaid_data(db))
    except Exception as e:
        raise HTTPException(502, f"Plaid reset error: {e}") from e


@router.get("/sync/health", response_model=SyncHealthResponse)
def sync_health(db: Session = Depends(get_db)) -> SyncHealthResponse:
    return SyncHealthResponse(**build_health_summary(db))


def _sync_response(db: Session, result: dict) -> PlaidSyncResponse:
    health = store_sync_health(db, result)
    from app.services.net_worth_snapshots import capture_snapshot

    if result.get("ran"):
        capture_snapshot(db)
    payload = {**result, "health": health}
    return PlaidSyncResponse(**payload)


@router.post("/sync", response_model=PlaidSyncResponse)
def sync_plaid(db: Session = Depends(get_db)) -> PlaidSyncResponse:
    _require_plaid()
    try:
        result = plaid_sync.sync_all(db, force=True)
        return _sync_response(db, result)
    except Exception as e:
        raise HTTPException(502, f"Plaid sync error: {e}") from e


@router.post("/sync/scheduled", response_model=PlaidSyncResponse)
def sync_plaid_scheduled(db: Session = Depends(get_db)) -> PlaidSyncResponse:
    _require_plaid()
    try:
        result = plaid_sync.run_scheduled_sync(db)
        return _sync_response(db, result)
    except Exception as e:
        raise HTTPException(502, f"Plaid sync error: {e}") from e
