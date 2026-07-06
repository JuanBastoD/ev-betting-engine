"""Composition-root tests: the build_* functions produce correctly-typed,
correctly-configured objects; get_* Depends() adapters delegate to them.

`build_run_pipeline_use_case` is exercised with the real (httpx-backed)
providers it constructs internally - safe because constructing an
`httpx.AsyncClient`/`TheOddsApiClient`/`SportmonksClient` never makes a
network call by itself, only invoking one of its methods would (which this
test never does).
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.use_cases.list_value_bets import ListValueBetsUseCase
from src.application.use_cases.run_pipeline import RunPipelineUseCase
from src.domain.ports.match_repository import MatchRepository
from src.domain.services.market_model.detector import MarketValueDetector
from src.domain.services.match_model.match_value_detector import ConfirmationMode, MatchValueDetector
from src.domain.services.player_props.player_prop_detector import PlayerPropDetector
from src.infrastructure.config import Settings
from src.infrastructure.persistence.models import Base
from src.presentation.api.dependencies import (
    build_market_value_detector,
    build_match_value_detector,
    build_player_prop_detector,
    build_run_pipeline_use_case,
    get_list_value_bets_use_case,
    get_local_odds_provider,
    get_match_repository,
    get_run_pipeline_use_case,
    get_settings,
)
from tests.fakes import FakeLocalOddsProvider


@pytest.fixture
def settings() -> Settings:
    return Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        ODDS_API_KEY="test-key",
        SPORTMONKS_API_TOKEN="test-token",
    )


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async_session = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        yield async_session
    finally:
        await async_session.close()
        await engine.dispose()


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_build_market_value_detector_uses_configured_thresholds(settings: Settings) -> None:
    detector = build_market_value_detector(settings)
    assert isinstance(detector, MarketValueDetector)


def test_build_match_value_detector_uses_configured_mode(settings: Settings) -> None:
    detector = build_match_value_detector(settings)
    assert isinstance(detector, MatchValueDetector)
    assert detector.mode is ConfirmationMode.CONFIRMATION


def test_build_match_value_detector_honors_independent_mode() -> None:
    settings = Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:", ODDS_API_KEY="k", SPORTMONKS_API_TOKEN="t",
        MATCH_CONFIRMATION_MODE="INDEPENDENT",
    )
    detector = build_match_value_detector(settings)
    assert detector.mode is ConfirmationMode.INDEPENDENT


def test_build_player_prop_detector(settings: Settings) -> None:
    detector = build_player_prop_detector(settings)
    assert isinstance(detector, PlayerPropDetector)


async def test_build_run_pipeline_use_case_wires_a_working_pipeline(
    settings: Settings, session: AsyncSession
) -> None:
    use_case = build_run_pipeline_use_case(session, settings, FakeLocalOddsProvider())
    result = await use_case.execute(matches=[])

    assert result.matches_processed == 0


async def test_get_run_pipeline_use_case_delegates_to_the_builder(
    settings: Settings, session: AsyncSession
) -> None:
    use_case = await get_run_pipeline_use_case(session, settings, FakeLocalOddsProvider())
    assert isinstance(use_case, RunPipelineUseCase)


async def test_get_list_value_bets_use_case_wires_a_real_repository(session: AsyncSession) -> None:
    use_case = await get_list_value_bets_use_case(session)
    assert isinstance(use_case, ListValueBetsUseCase)


async def test_get_match_repository_wires_a_real_repository(session: AsyncSession) -> None:
    repository = await get_match_repository(session)
    assert isinstance(repository, MatchRepository)


async def test_get_local_odds_provider_opens_and_closes_a_browser_session(settings: Settings) -> None:
    with patch("src.presentation.api.dependencies.PlaywrightBrowserSession") as fake_session_cls:
        fake_session = fake_session_cls.return_value
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)

        generator = get_local_odds_provider(settings)
        provider = await generator.__anext__()
        assert provider is not None

        with pytest.raises(StopAsyncIteration):
            await generator.__anext__()

        fake_session.__aenter__.assert_awaited_once()
        fake_session.__aexit__.assert_awaited_once()
