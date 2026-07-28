"""Persist and load per-profile JSON settings."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.profile_setting import ProfileSetting

DEFAULTS: dict[str, Any] = {
    "annual_income_override": None,
    "investing_pct_of_income": 20.0,
    "safety_net_pct_of_income": 10.0,
    "safety_net_account_id": None,
    "projection_horizon_years": 20,
    "stock_appreciation_pct": 7.0,
    "dividend_growth_pct": 3.0,
    "per_ticker_overrides": {},
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3.1:latest",
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from": "",
    "digest_enabled": True,
    "digest_email": "",
    "digest_day_of_week": "sun",
    "digest_hour": 18,
    "digest_timezone": "America/Los_Angeles",
    "alert_large_uncategorized": 500.0,
    "last_sync_health": None,
    "google_drive_refresh_token_enc": None,
    "google_drive_email": None,
    "google_drive_folder_id": None,
    "google_drive_last_backup_at": None,
}


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(ProfileSetting, key)
    if not row:
        return DEFAULTS.get(key, default)
    try:
        return json.loads(row.value)
    except json.JSONDecodeError:
        return DEFAULTS.get(key, default)


def set_setting(db: Session, key: str, value: Any) -> None:
    payload = json.dumps(value)
    row = db.get(ProfileSetting, key)
    if row:
        row.value = payload
    else:
        db.add(ProfileSetting(key=key, value=payload))
    db.commit()


def get_all_settings(db: Session) -> dict[str, Any]:
    out = dict(DEFAULTS)
    for row in db.query(ProfileSetting).all():
        try:
            out[row.key] = json.loads(row.value)
        except json.JSONDecodeError:
            continue
    return out


def update_settings(db: Session, patch: dict[str, Any]) -> dict[str, Any]:
    for key, value in patch.items():
        if key in DEFAULTS or key.startswith("custom_goal_"):
            set_setting(db, key, value)
    return get_all_settings(db)
