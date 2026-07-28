from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def alembic_config(database_url: str) -> Config:
    root = Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    if database_url.startswith("sqlite"):
        db_path = database_url.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return cfg


def upgrade_database(database_url: str) -> None:
    cfg = alembic_config(database_url)
    cfg.attributes["keep_sqlalchemy_url"] = True
    command.upgrade(cfg, "head")
