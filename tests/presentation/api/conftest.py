"""FastAPI test app: real SqlAlchemy repositories against an in-memory
SQLite engine (StaticPool, same pattern as
tests/infrastructure/persistence/conftest.py) + fake providers (no
network, no browser) wired in through `app.dependency_overrides`.

`get_run_pipeline_use_case` is overridden as a whole (rather than
overriding the individual provider dependencies it would use in
production) because `build_run_pipeline_use_case` constructs the real
`TheOddsApiSharpOddsProvider`/`SportmonksPlayerStatsProvider`/etc.
providers *inside itself*, not via separate `Depends()` functions - see
`dependencies.py`'s own docstring for why. The override still exercises
the real detector-construction helpers (`build_match_value_detector`,
etc.) and real repositories, just with fake data sources standing in for
external APIs/the browser.
"""

from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.use_cases.detect_match_value_bets import DetectMatchValueBetsUseCase
from src.application.use_cases.detect_player_prop_value_bets import (
    DetectPlayerPropValueBetsUseCase,
)
from src.application.use_cases.ingest_local_odds import IngestLocalOddsUseCase
from src.application.use_cases.ingest_player_stats import IngestPlayerStatsUseCase
from src.application.use_cases.ingest_sharp_odds import IngestSharpOddsUseCase
from src.application.use_cases.list_value_bets import ListValueBetsUseCase
from src.application.use_cases.run_pipeline import RunPipelineUseCase
from src.infrastructure.config import Settings
from src.infrastructure.persistence.models import Base
from src.infrastructure.persistence.repositories.match_repository import SqlAlchemyMatchRepository
from src.infrastructure.persistence.repositories.odds_repository import SqlAlchemyOddsRepository
from src.infrastructure.persistence.repositories.player_repository import SqlAlchemyPlayerRepository
from src.infrastructure.persistence.repositories.player_stats_repository import (
    SqlAlchemyPlayerStatsRepository,
)
from src.infrastructure.persistence.repositories.value_bet_repository import (
    SqlAlchemyValueBetRepository,
)
from src.infrastructure.persistence.session import get_session
from src.presentation.api.app import create_app
from src.presentation.api.dependencies import (
    build_match_value_detector,
    build_player_prop_detector,
    get_list_value_bets_use_case,
    get_match_repository,
    get_run_pipeline_use_case,
    get_settings,
)
from tests.fakes import (
    FakeLocalOddsProvider,
    FakePlayerStatsProvider,
    FakeSharpOddsProvider,
    FakeStatsProvider,
)


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        ODDS_API_KEY="test-key",
        SPORTMONKS_API_TOKEN="test-token",
        LEAGUE_AVERAGE_GOALS=1.0,
    )


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
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
        await test_engine.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    async_session = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        yield async_session
    finally:
        await async_session.close()


@pytest.fixture
def fake_sharp_odds_provider() -> FakeSharpOddsProvider:
    return FakeSharpOddsProvider()


@pytest.fixture
def fake_stats_provider() -> FakeStatsProvider:
    return FakeStatsProvider()


@pytest.fixture
def fake_local_odds_provider() -> FakeLocalOddsProvider:
    return FakeLocalOddsProvider()


@pytest.fixture
def fake_player_stats_provider() -> FakePlayerStatsProvider:
    return FakePlayerStatsProvider()


@pytest.fixture
def app(
    session: AsyncSession,
    test_settings: Settings,
    fake_sharp_odds_provider: FakeSharpOddsProvider,
    fake_stats_provider: FakeStatsProvider,
    fake_local_odds_provider: FakeLocalOddsProvider,
    fake_player_stats_provider: FakePlayerStatsProvider,
) -> FastAPI:
    test_app = create_app()

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield session

    def override_get_settings() -> Settings:
        return test_settings

    async def override_get_run_pipeline_use_case() -> RunPipelineUseCase:
        match_repository = SqlAlchemyMatchRepository(session)
        odds_repository = SqlAlchemyOddsRepository(session)
        player_repository = SqlAlchemyPlayerRepository(session)
        player_stats_repository = SqlAlchemyPlayerStatsRepository(session)
        value_bet_repository = SqlAlchemyValueBetRepository(session)

        return RunPipelineUseCase(
            match_repository=match_repository,
            ingest_sharp_odds=IngestSharpOddsUseCase(
                sharp_odds_provider=fake_sharp_odds_provider,
                stats_provider=fake_stats_provider,
                match_repository=match_repository,
                odds_repository=odds_repository,
            ),
            ingest_local_odds=IngestLocalOddsUseCase(
                local_odds_provider=fake_local_odds_provider, odds_repository=odds_repository
            ),
            ingest_player_stats=IngestPlayerStatsUseCase(
                player_stats_provider=fake_player_stats_provider,
                player_repository=player_repository,
                player_stats_repository=player_stats_repository,
            ),
            detect_match_value_bets=DetectMatchValueBetsUseCase(
                match_value_detector=build_match_value_detector(test_settings),
                value_bet_repository=value_bet_repository,
                league_average_goals=test_settings.league_average_goals,
            ),
            detect_player_prop_value_bets=DetectPlayerPropValueBetsUseCase(
                player_prop_detector=build_player_prop_detector(test_settings),
                value_bet_repository=value_bet_repository,
            ),
        )

    async def override_get_list_value_bets_use_case() -> ListValueBetsUseCase:
        return ListValueBetsUseCase(value_bet_repository=SqlAlchemyValueBetRepository(session))

    async def override_get_match_repository() -> SqlAlchemyMatchRepository:
        return SqlAlchemyMatchRepository(session)

    test_app.dependency_overrides[get_session] = override_get_session
    test_app.dependency_overrides[get_settings] = override_get_settings
    test_app.dependency_overrides[get_run_pipeline_use_case] = override_get_run_pipeline_use_case
    test_app.dependency_overrides[get_list_value_bets_use_case] = override_get_list_value_bets_use_case
    test_app.dependency_overrides[get_match_repository] = override_get_match_repository
    return test_app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
