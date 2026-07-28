import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.services.seed import seed_chart_of_accounts


@pytest.fixture(autouse=True)
def disable_live_market_quotes(monkeypatch):
    monkeypatch.setenv("LIVE_MARKET_QUOTES_ENABLED", "false")
    from app.config import _load_settings

    _load_settings.cache_clear()
    yield
    _load_settings.cache_clear()


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    seed_chart_of_accounts(session)
    yield session
    session.close()
