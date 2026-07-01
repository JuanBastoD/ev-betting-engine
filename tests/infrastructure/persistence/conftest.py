from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.league import League
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.selection import Selection
from src.domain.entities.team import Team
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


@pytest.fixture
def home_team() -> Team:
    return Team(id="team-home", name="River Plate", country="Argentina")


@pytest.fixture
def away_team() -> Team:
    return Team(id="team-away", name="Boca Juniors", country="Argentina")


@pytest.fixture
def league() -> League:
    return League(id="league-1", name="Liga Profesional", country="Argentina")


@pytest.fixture
def kickoff_utc() -> datetime:
    return datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc)


@pytest.fixture
def match(home_team: Team, away_team: Team, league: League, kickoff_utc: datetime) -> Match:
    return Match(
        id="match-1",
        home_team=home_team,
        away_team=away_team,
        league=league,
        kickoff_utc=kickoff_utc,
    )


@pytest.fixture
def bookmaker() -> Bookmaker:
    return Bookmaker(name="Pinnacle", is_sharp=True, region="EU")


@pytest.fixture
def selection() -> Selection:
    return Selection(market_type=MarketType.MATCH_WINNER_1X2, outcome="Home")
