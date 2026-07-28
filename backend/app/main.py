from pathlib import Path

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import api_router
from app.config import get_settings
from app.db.registry import init_registry_database
from app.services.app_config import apply_app_config_to_environ

logger = logging.getLogger(__name__)
apply_app_config_to_environ()
settings = get_settings()

app = FastAPI(
    title="Personal Finance",
    description="Local-first ledger with quarterly financial statements",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

_scheduler = None


def _run_weekly_digest_job() -> None:
    from app.db.profile_db import get_profile_session_factory
    from app.db.registry import get_registry_session_factory
    from app.models.profile import Profile
    from app.services.weekly_digest import send_weekly_digest

    registry = get_registry_session_factory()()
    try:
        profiles = registry.query(Profile).order_by(Profile.email).all()
    finally:
        registry.close()

    for profile in profiles:
        factory = get_profile_session_factory(profile.id)
        db = factory()
        try:
            result = send_weekly_digest(db)
            logger.info("Weekly digest for %s: %s", profile.email, result.get("status"))
        except Exception:
            logger.exception("Weekly digest failed for %s", profile.email)
        finally:
            db.close()


def _start_schedulers() -> None:
    """Plaid cloud sync (optional) + always-on weekly digest (local APScheduler)."""
    global _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    settings = get_settings()
    _scheduler = BackgroundScheduler(timezone="UTC")

    if settings.cloud_scheduler_enabled:
        if not settings.plaid_enabled or not settings.plaid_configured:
            logger.warning("Cloud scheduler enabled but Plaid is not configured")
        else:
            from app.services.plaid_scheduler import sync_all_profiles

            def _job() -> None:
                logger.info("Cloud scheduler: starting Plaid sync for all profiles")
                sync_all_profiles(force=False)

            _scheduler.add_job(
                _job,
                CronTrigger(
                    hour=settings.cloud_scheduler_hour_utc,
                    minute=settings.cloud_scheduler_minute_utc,
                ),
                id="plaid_daily_sync",
                replace_existing=True,
            )
            logger.info(
                "Plaid cloud sync scheduled daily %02d:%02d UTC",
                settings.cloud_scheduler_hour_utc,
                settings.cloud_scheduler_minute_utc,
            )

    # Weekly digest always available locally (same Gmail SMTP pattern as hedge fund).
    _scheduler.add_job(
        _run_weekly_digest_job,
        CronTrigger(day_of_week="sun", hour=18, minute=0, timezone="America/Los_Angeles"),
        id="weekly_digest",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Weekly digest scheduled Sunday 18:00 America/Los_Angeles")


def _stop_schedulers() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


@app.on_event("startup")
def on_startup() -> None:
    init_registry_database()
    _start_schedulers()


@app.on_event("shutdown")
def on_shutdown() -> None:
    _stop_schedulers()


# Repo root: backend/app/main.py -> parents[2]
REPO_ROOT = Path(__file__).resolve().parents[2]
DIST = REPO_ROOT / "frontend" / "dist"
PUBLIC = REPO_ROOT / "frontend" / "public"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/oauth/google-drive.html", include_in_schema=False)
def google_drive_oauth_page():
    path = PUBLIC / "oauth" / "google-drive.html"
    if not path.is_file():
        raise HTTPException(404, "OAuth callback page missing")
    return FileResponse(path)


def _mount_ui() -> None:
    if not DIST.joinpath("index.html").is_file():
        return

    index = DIST / "index.html"
    assets = DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    # Client-side routes (React Router) — must return index.html, not 404 JSON.
    SPA_ROUTES = frozenset(
        {
            "accounts",
            "register",
            "reconcile",
            "reports",
            "settings",
            "goals",
            "advisor",
            "review/duplicates",
            "rules",
            "login",
            "login/register",
            "login/forgot-password",
        }
    )

    @app.get("/", include_in_schema=False)
    async def spa_root():
        return FileResponse(index)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path in (
            "health",
            "docs",
            "openapi.json",
            "redoc",
        ):
            raise HTTPException(404)
        if full_path in SPA_ROUTES or not (DIST / full_path).is_file():
            return FileResponse(index)
        return FileResponse(DIST / full_path)


_mount_ui()
