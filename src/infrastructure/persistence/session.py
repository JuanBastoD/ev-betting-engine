"""Async engine/session factory for the persistence layer.

`get_session` is the injectable dependency other layers (use cases, a future
API layer) depend on to obtain a session per unit of work. It never commits
on the caller's behalf - see the repository docstrings for why.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.infrastructure.config import Settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine(database_url: str) -> AsyncEngine:
    """Build an async engine for `database_url`.

    Whether this points at `sqlite+aiosqlite:///...` (dev/tests) or
    `postgresql+asyncpg://...` (prod) is entirely decided by the URL string -
    no code path here is backend-specific.
    """
    return create_async_engine(database_url)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, expire_on_commit=False)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory, creating it from `Settings()`
    on first use so the underlying engine/connection pool is created once and
    reused, not per call."""
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_engine(Settings().database_url)
        _session_factory = create_session_factory(_engine)
    return _session_factory


async def reset_session_factory() -> None:
    """Dispose the cached engine and forget it. Used at app shutdown and by tests."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
