from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from src.infrastructure.persistence.models import Base


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """A fresh in-memory SQLite engine with the full schema created.

    StaticPool is required for `:memory:` SQLite: without it, each checked-out
    connection would see its own empty database, since SQLite's in-memory
    database is scoped to a single connection.
    """
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield test_engine
    finally:
        async with test_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await test_engine.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """A session bound to a single connection/transaction that is always
    rolled back at teardown, isolating tests even though repositories may
    flush (they never commit - see repositories/*.py docstrings).
    """
    connection = await engine.connect()
    transaction = await connection.begin()
    async_session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        yield async_session
    finally:
        await async_session.close()
        await transaction.rollback()
        await connection.close()
