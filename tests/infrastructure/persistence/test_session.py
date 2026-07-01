from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.persistence.session import (
    create_engine,
    create_session_factory,
    get_session,
    get_session_factory,
    reset_session_factory,
)


@pytest_asyncio.fixture(autouse=True)
async def _reset_session_factory() -> AsyncGenerator[None, None]:
    await reset_session_factory()
    yield
    await reset_session_factory()


async def test_create_engine_and_session_factory_produce_a_working_session() -> None:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    session_factory = create_session_factory(engine)

    assert isinstance(session_factory, async_sessionmaker)

    async with session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1

    await engine.dispose()


async def test_get_session_yields_a_working_session_configured_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ODDS_API_KEY", "test-key")
    monkeypatch.setenv("SPORTMONKS_API_TOKEN", "test-token")

    async for session in get_session():
        assert isinstance(session, AsyncSession)
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1


async def test_get_session_factory_reuses_the_same_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ODDS_API_KEY", "test-key")
    monkeypatch.setenv("SPORTMONKS_API_TOKEN", "test-token")

    first = get_session_factory()
    second = get_session_factory()

    assert first is second
