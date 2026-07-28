from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models.profile import Profile, RegistryBase

_registry_engine = None
_RegistrySession: sessionmaker | None = None


def registry_database_url() -> str:
    settings = get_settings()
    path = settings.registry_database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def get_registry_engine():
    global _registry_engine, _RegistrySession
    if _registry_engine is None:
        _registry_engine = create_engine(
            registry_database_url(),
            connect_args={"check_same_thread": False},
        )
        _RegistrySession = sessionmaker(autocommit=False, autoflush=False, bind=_registry_engine)
    return _registry_engine


def get_registry_session_factory() -> sessionmaker:
    get_registry_engine()
    assert _RegistrySession is not None
    return _RegistrySession


def _migrate_registry_schema(engine) -> None:
    insp = inspect(engine)
    if not insp.has_table("profiles"):
        return
    cols = {c["name"] for c in insp.get_columns("profiles")}
    with engine.begin() as conn:
        if "recovery_code_hash" not in cols:
            conn.execute(
                text("ALTER TABLE profiles ADD COLUMN recovery_code_hash VARCHAR(255)")
            )


def init_registry_database() -> None:
    engine = get_registry_engine()
    RegistryBase.metadata.create_all(bind=engine)
    _migrate_registry_schema(engine)


def profile_ledger_path(profile_id: str) -> Path:
    settings = get_settings()
    path = settings.profiles_dir / profile_id / "ledger.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
