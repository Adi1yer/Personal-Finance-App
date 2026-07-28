"""Local bring-your-own app config (Plaid / Google / encryption), gitignored."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from app.config import REPO_ROOT, get_settings

CONFIG_PATH = REPO_ROOT / "data" / "app_config.json"

_ALLOWED_KEYS = frozenset(
    {
        "encryption_key",
        "jwt_secret",
        "plaid_client_id",
        "plaid_secret",
        "plaid_env",
        "plaid_enabled",
        "plaid_redirect_uri",
        "google_oauth_client_id",
        "google_oauth_client_secret",
        "google_oauth_redirect_uri",
    }
)

_SECRET_KEYS = frozenset(
    {
        "encryption_key",
        "jwt_secret",
        "plaid_secret",
        "google_oauth_client_secret",
    }
)


def _ensure_data_dir() -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_app_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_app_config(patch: dict[str, Any]) -> dict[str, Any]:
    """Merge patch into app_config.json and apply to process env for live reload."""
    _ensure_data_dir()
    current = load_app_config()
    for key, value in patch.items():
        if key not in _ALLOWED_KEYS:
            continue
        if value is None or value == "":
            current.pop(key, None)
            os.environ.pop(key.upper(), None)
            continue
        if key == "plaid_enabled":
            current[key] = bool(value) if not isinstance(value, str) else value.lower() in (
                "1",
                "true",
                "yes",
            )
        else:
            current[key] = str(value).strip()
        env_key = key.upper()
        os.environ[env_key] = (
            "true" if isinstance(current[key], bool) and current[key] else str(current[key])
        )
    CONFIG_PATH.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    # Force settings cache refresh
    from app.config import _load_settings

    _load_settings.cache_clear()
    return current


def apply_app_config_to_environ() -> None:
    """Call at process start so Settings picks up BYO values."""
    cfg = load_app_config()
    for key, value in cfg.items():
        if key not in _ALLOWED_KEYS:
            continue
        env_key = key.upper()
        if env_key not in os.environ or not os.environ.get(env_key):
            os.environ[env_key] = (
                "true" if isinstance(value, bool) and value else str(value)
            )


def ensure_encryption_key() -> str:
    settings = get_settings()
    if settings.encryption_key:
        return settings.encryption_key
    cfg = load_app_config()
    if cfg.get("encryption_key"):
        apply_app_config_to_environ()
        from app.config import _load_settings

        _load_settings.cache_clear()
        return str(cfg["encryption_key"])
    key = Fernet.generate_key().decode()
    save_app_config({"encryption_key": key})
    return key


def _mask(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "••••••••"
    return value[:4] + "…" + value[-4:]


def setup_status() -> dict[str, Any]:
    apply_app_config_to_environ()
    from app.config import _load_settings

    _load_settings.cache_clear()
    settings = get_settings()
    cfg = load_app_config()
    return {
        "encryption_key_set": bool(settings.encryption_key),
        "plaid": {
            "configured": settings.plaid_configured,
            "enabled": settings.plaid_enabled,
            "env": settings.plaid_env,
            "client_id_set": bool(settings.plaid_client_id),
            "secret_set": bool(settings.plaid_secret),
            "client_id_masked": _mask(settings.plaid_client_id or None),
            "redirect_uri": settings.plaid_redirect_uri
            or (
                f"https://{settings.api_host}:{settings.api_port}/oauth/plaid.html"
                if settings.plaid_env == "production"
                else f"http://{settings.api_host}:{settings.api_port}/oauth/plaid.html"
            ),
        },
        "google_drive": {
            "configured": settings.google_drive_configured,
            "client_id_set": bool(settings.google_oauth_client_id),
            "secret_set": bool(settings.google_oauth_client_secret),
            "client_id_masked": _mask(settings.google_oauth_client_id or None),
            "redirect_uri": settings.google_oauth_redirect_uri,
        },
        "config_file": str(CONFIG_PATH.relative_to(REPO_ROOT)) if CONFIG_PATH.exists() else None,
        "has_local_overrides": bool(cfg),
    }
