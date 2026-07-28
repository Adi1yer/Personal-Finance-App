from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{REPO_ROOT / 'data' / 'finance.db'}"
    registry_database_path: Path = REPO_ROOT / "data" / "registry.db"
    profiles_dir: Path = REPO_ROOT / "data" / "profiles"
    jwt_secret: str = ""
    jwt_expire_hours: int = 24 * 30
    encryption_key: str = ""
    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"
    plaid_enabled: bool = False
    plaid_redirect_uri: str = ""
    plaid_transactions_sync_days: int = 7
    plaid_holdings_sync_days: int = 1
    live_market_quotes_enabled: bool = True
    cloud_scheduler_enabled: bool = False
    cloud_scheduler_hour_utc: int = 6
    cloud_scheduler_minute_utc: int = 0
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,https://127.0.0.1:8000,https://localhost:8000"
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = "https://localhost:8000/oauth/google-drive.html"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def plaid_configured(self) -> bool:
        return bool(self.plaid_client_id and self.plaid_secret and self.encryption_key)

    @property
    def google_drive_configured(self) -> bool:
        return bool(
            self.google_oauth_client_id
            and self.google_oauth_client_secret
            and self.encryption_key
        )

    @property
    def effective_jwt_secret(self) -> str:
        if self.jwt_secret:
            return self.jwt_secret
        if self.encryption_key:
            return self.encryption_key
        return "personal-finance-local-dev-change-in-env"


_ENV_FILE = REPO_ROOT / ".env"
_env_mtime: float | None = None


def get_settings() -> Settings:
    """Load settings; re-read .env when the file changes (no full app restart needed)."""
    global _env_mtime
    mtime = _ENV_FILE.stat().st_mtime if _ENV_FILE.is_file() else None
    if mtime != _env_mtime:
        _env_mtime = mtime
        _load_settings.cache_clear()
    return _load_settings()


@lru_cache
def _load_settings() -> Settings:
    return Settings()
