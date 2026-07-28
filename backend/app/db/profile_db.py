from __future__ import annotations

import sqlite3
import threading
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.migrate import upgrade_database
from app.db.registry import profile_ledger_path
from app.services.seed import seed_chart_of_accounts

_engines: dict[str, object] = {}
_session_factories: dict[str, sessionmaker] = {}
_migrated_profiles: set[str] = set()
_migration_lock = threading.Lock()


def profile_database_url(profile_id: str) -> str:
    return f"sqlite:///{profile_ledger_path(profile_id)}"


def _clear_profile_engine_cache(profile_id: str) -> None:
    _session_factories.pop(profile_id, None)
    engine = _engines.pop(profile_id, None)
    if engine is not None:
        engine.dispose()  # type: ignore[union-attr]


def _ledger_has_schema(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='account'"
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _head_revision() -> str:
    """Current Alembic head — keep migration checks in sync automatically."""
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[2]
    script = ScriptDirectory(str(root / "alembic"))
    head = script.get_current_head()
    if not head:
        raise RuntimeError("No Alembic head revision found")
    return head


def _needs_migration(path: Path) -> bool:
    if not _ledger_has_schema(path):
        return True
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        if row is None:
            return True
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        if version is None:
            return True
        return version[0] != _head_revision()
    finally:
        conn.close()


def ensure_profile_ledger_schema(profile_id: str) -> None:
    """Run Alembic migrations once per process when the profile DB is new or behind."""
    if profile_id in _migrated_profiles:
        return

    with _migration_lock:
        if profile_id in _migrated_profiles:
            return

        path = profile_ledger_path(profile_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.stat().st_size == 0:
            path.unlink()
        if not _needs_migration(path):
            _migrated_profiles.add(profile_id)
            return

        _clear_profile_engine_cache(profile_id)
        upgrade_database(profile_database_url(profile_id))
        _migrated_profiles.add(profile_id)


def get_profile_session_factory(profile_id: str) -> sessionmaker:
    ensure_profile_ledger_schema(profile_id)
    if profile_id not in _session_factories:
        url = profile_database_url(profile_id)
        engine = create_engine(url, connect_args={"check_same_thread": False})
        _engines[profile_id] = engine
        _session_factories[profile_id] = sessionmaker(
            autocommit=False, autoflush=False, bind=engine
        )
    return _session_factories[profile_id]


def init_profile_ledger(profile_id: str) -> None:
    """Ensure schema exists and seed categories + system accounts if empty."""
    ensure_profile_ledger_schema(profile_id)
    factory = get_profile_session_factory(profile_id)
    db = factory()
    try:
        from app.models.account import Account

        if db.query(Account).first() is None:
            seed_chart_of_accounts(db)
    finally:
        db.close()


def get_profile_db(profile_id: str) -> Generator[Session, None, None]:
    factory = get_profile_session_factory(profile_id)
    db = factory()
    try:
        yield db
    finally:
        db.close()
