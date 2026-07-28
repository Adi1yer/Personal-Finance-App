"""Short-lived Google Drive OAuth pending states."""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

SESSION_TTL = timedelta(minutes=30)


@dataclass
class PendingGoogleAuth:
    profile_id: str
    state: str
    code_verifier: str
    created_at: datetime


_lock = threading.Lock()
_by_state: dict[str, PendingGoogleAuth] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_pending(profile_id: str, code_verifier: str) -> str:
    state = secrets.token_urlsafe(24)
    with _lock:
        _by_state[state] = PendingGoogleAuth(
            profile_id=profile_id,
            state=state,
            code_verifier=code_verifier,
            created_at=_utc_now(),
        )
    return state


def pop_pending(state: str) -> PendingGoogleAuth | None:
    with _lock:
        session = _by_state.pop(state, None)
    if not session:
        return None
    if _utc_now() - session.created_at > SESSION_TTL:
        return None
    return session
