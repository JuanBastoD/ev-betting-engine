"""Lifespan tests: the DB pool is created on startup and disposed on
shutdown, and the scheduler is started/stopped around the same window.
Real `Settings()`/DB engine (in-memory SQLite) and a mocked scheduler (so
no periodic job actually gets registered against a live APScheduler loop
beyond what's needed to prove start()/shutdown() were called).
"""

from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure.persistence import session as session_module
from src.presentation.api.app import create_app, lifespan


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ODDS_API_KEY", "test-key")
    monkeypatch.setenv("SPORTMONKS_API_TOKEN", "test-token")


@pytest.fixture(autouse=True)
def _reset_session_factory():
    yield
    session_module._engine = None
    session_module._session_factory = None


def test_create_app_builds_without_error() -> None:
    # Route reachability (/health, /pipeline/run, /value-bets/query,
    # /value-bets) is exercised end to end by the other test_*.py files in
    # this package via the real app - this just confirms construction
    # itself (exception handlers + all three routers) doesn't raise.
    app = create_app()
    assert app.title == "ev-betting-engine"


async def test_lifespan_initializes_and_tears_down_the_db_pool_and_scheduler() -> None:
    fake_scheduler = MagicMock()

    with patch("src.presentation.api.app.create_scheduler", return_value=fake_scheduler):
        app = create_app()
        async with lifespan(app):
            assert session_module._session_factory is not None
            fake_scheduler.start.assert_called_once()

    fake_scheduler.shutdown.assert_called_once_with(wait=False)
    assert session_module._session_factory is None
