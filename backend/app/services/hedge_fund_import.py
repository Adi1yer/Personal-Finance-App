"""Import Ollama/SMTP defaults from the sibling ai-hedge-fund-production project."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.services.profile_settings import get_all_settings, get_setting, set_setting

HEDGE_FUND_ROOT = Path.home() / "ai-hedge-fund-production"
HEDGE_ENV_PATH = HEDGE_FUND_ROOT / ".env"

_ENV_MAP = {
    "SMTP_SERVER": "smtp_host",
    "SMTP_PORT": "smtp_port",
    "SENDER_EMAIL": "smtp_user",
    "SENDER_PASSWORD": "smtp_password",
    "RECIPIENT_EMAIL": "digest_email",
}


def _parse_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _is_blank(value: Any) -> bool:
    return value is None or value == ""


def import_hedge_fund_settings(db: Session, *, overwrite: bool = False) -> dict[str, Any]:
    """
    Seed SMTP (+ digest recipient) from hedge-fund .env when local settings are empty.
    Never logs secret values.
    """
    env = _parse_dotenv(HEDGE_ENV_PATH)
    if not env:
        return {"imported": [], "source": None, "reason": "hedge_env_missing"}

    current = get_all_settings(db)
    imported: list[str] = []

    for env_key, setting_key in _ENV_MAP.items():
        raw = (env.get(env_key) or "").strip()
        if not raw:
            continue
        if not overwrite and not _is_blank(current.get(setting_key)):
            continue
        value: Any = int(raw) if setting_key == "smtp_port" else raw
        set_setting(db, setting_key, value)
        imported.append(setting_key)

    if get_setting(db, "smtp_user") and _is_blank(get_setting(db, "smtp_from")):
        set_setting(db, "smtp_from", get_setting(db, "smtp_user"))
        imported.append("smtp_from")

    model = get_setting(db, "ollama_model")
    if overwrite or model in (None, "", "qwen2.5:7b"):
        set_setting(db, "ollama_model", "llama3.1:latest")
        if "ollama_model" not in imported:
            imported.append("ollama_model")

    refreshed = get_all_settings(db)
    return {
        "imported": imported,
        "source": str(HEDGE_ENV_PATH),
        "smtp_ready": bool(
            refreshed.get("smtp_host")
            and refreshed.get("smtp_user")
            and refreshed.get("smtp_password")
        ),
    }


def hedge_env_available() -> bool:
    return HEDGE_ENV_PATH.is_file()
