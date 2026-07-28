"""Google OAuth helpers for Drive backups (Desktop / installed client)."""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import get_settings

SCOPES = (
    "https://www.googleapis.com/auth/drive.file "
    "https://www.googleapis.com/auth/userinfo.email "
    "openid"
)
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def build_auth_url(*, state: str, code_challenge: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def make_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge)."""
    return _pkce_pair()


def exchange_code(code: str, *, code_verifier: str) -> dict[str, Any]:
    settings = get_settings()
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            TOKEN_URL,
            data={
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_oauth_redirect_uri,
            },
        )
        if res.status_code >= 400:
            raise ValueError(f"Token exchange failed: {res.text}")
        return res.json()


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    settings = get_settings()
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            TOKEN_URL,
            data={
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if res.status_code >= 400:
            raise ValueError(f"Token refresh failed: {res.text}")
        return res.json()


def fetch_email(access_token: str) -> str | None:
    with httpx.Client(timeout=20.0) as client:
        res = client.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if res.status_code >= 400:
            return None
        data = res.json()
        email = data.get("email")
        return str(email) if email else None
