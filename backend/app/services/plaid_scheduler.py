"""Background Plaid sync for all registered profiles (cloud / always-on server)."""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.db.profile_db import get_profile_session_factory
from app.db.registry import get_registry_session_factory
from app.models.profile import Profile
from app.services.plaid_sync import sync_all

logger = logging.getLogger(__name__)


def sync_all_profiles(*, force: bool = False) -> list[dict[str, Any]]:
    """Run Plaid sync for every profile. Used by the cloud scheduler and CLI."""
    settings = get_settings()
    if not settings.plaid_enabled or not settings.plaid_configured:
        logger.info("Plaid sync skipped: not configured")
        return []

    registry = get_registry_session_factory()()
    results: list[dict[str, Any]] = []
    try:
        profiles = registry.query(Profile).order_by(Profile.email).all()
        for profile in profiles:
            db = get_profile_session_factory(profile.id)()
            try:
                outcome = sync_all(db, force=force)
                outcome["profile_id"] = profile.id
                outcome["email"] = profile.email
                results.append(outcome)
                if outcome.get("ran"):
                    logger.info(
                        "Plaid sync %s: posted=%s holdings=%s",
                        profile.email,
                        outcome.get("posted"),
                        outcome.get("holdings_updated"),
                    )
                else:
                    logger.info("Plaid sync %s: up to date", profile.email)
            except Exception:
                logger.exception("Plaid sync failed for profile %s", profile.email)
                results.append(
                    {
                        "profile_id": profile.id,
                        "email": profile.email,
                        "ran": False,
                        "error": True,
                    }
                )
            finally:
                db.close()
    finally:
        registry.close()

    return results
