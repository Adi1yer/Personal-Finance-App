"""Short-lived Plaid Link sessions for browser-based bank connection."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

SESSION_TTL = timedelta(minutes=30)


@dataclass
class PendingBrowserLink:
    profile_id: str
    link_token: str
    created_at: datetime


_lock = threading.Lock()
_sessions: dict[str, PendingBrowserLink] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def save_browser_link(profile_id: str, link_token: str) -> None:
    with _lock:
        _sessions[profile_id] = PendingBrowserLink(
            profile_id=profile_id,
            link_token=link_token,
            created_at=_utc_now(),
        )


def get_browser_link(profile_id: str | None = None) -> PendingBrowserLink | None:
    with _lock:
        if profile_id:
            session = _sessions.get(profile_id)
        else:
            session = None
            latest: datetime | None = None
            for candidate in _sessions.values():
                if latest is None or candidate.created_at > latest:
                    session = candidate
                    latest = candidate.created_at
        if not session:
            return None
        if _utc_now() - session.created_at > SESSION_TTL:
            _sessions.pop(session.profile_id, None)
            return None
        return session


def clear_browser_link(profile_id: str) -> None:
    with _lock:
        _sessions.pop(profile_id, None)
