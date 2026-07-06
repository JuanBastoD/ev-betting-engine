"""Composition root: the ONLY place concrete infrastructure/domain-service
implementations are chosen and wired together. Every use case and detector
downstream depends on a domain port or a `MatchStatisticalModel`/
`PlayerPropsModel` *interface* - never on `TheOddsApiClient`,
`SqlAlchemyMatchRepository`, `DixonColesModel`, or `PoissonPropsModel`
directly. Swapping in a future trained model (Prompt 10) means changing
exactly the two lines marked below, nowhere else.

Two layers, deliberately kept separate:
- `build_*` functions take their dependencies as *plain arguments* (a
  session, `Settings`, a provider) and do the actual wiring. They know
  nothing about FastAPI.
- `get_*` functions are thin FastAPI `Depends()` adapters over the
  `build_*` functions, resolving `session`/`settings`/providers through
  FastAPI's per-request DI.

This split exists because the scheduler (`scheduler.py`) needs to build the
exact same use case graph *outside* of a FastAPI request - `Depends(...)`
default values are only resolved by FastAPI's own machinery, not by
calling a `get_*` function directly. The scheduler calls the `build_*`
functions itself, supplying its own session/provider lifecycle; the API
routes get there via `Depends()`. Neither path duplicates the wiring logic.
"""

from collections.abc import AsyncGenerator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.detect_match_value_bets import DetectMatchValueBetsUseCase
from src.application.use_cases.detect_player_prop_value_bets import (
    DetectPlayerPropValueBetsUseCase,
)
from src.application.use_cases.ingest_local_odds import IngestLocalOddsUseCase
from src.application.use_cases.ingest_player_stats import IngestPlayerStatsUseCase
from src.application.use_cases.ingest_sharp_odds import IngestSharpOddsUseCase
from src.application.use_cases.list_value_bets import ListValueBetsUseCase
from src.application.use_cases.run_pipeline import RunPipelineUseCase
from src.domain.ports.local_odds_provider import LocalOddsProvider
from src.domain.ports.match_repository import MatchRepository
from src.domain.services.market_model.detector import MarketValueDetector
from src.domain.services.market_model.devig import MultiplicativeDevig
from src.domain.services.match_model.match_value_detector import ConfirmationMode, MatchValueDetector
from src.domain.services.match_model.xg_model import DixonColesModel  # noqa: F401  (Prompt 10 swap point)
from src.domain.services.player_props.player_prop_detector import PlayerPropDetector
from src.domain.services.player_props.player_model import PoissonPropsModel  # noqa: F401  (Prompt 10 swap point)
from src.infrastructure.config import Settings
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
from src.infrastructure.providers.api.client import TheOddsApiClient
from src.infrastructure.providers.api.player_stats.client import SportmonksClient
from src.infrastructure.providers.api.player_stats.provider import SportmonksPlayerStatsProvider
from src.infrastructure.providers.api.sharp_odds_provider import TheOddsApiSharpOddsProvider
from src.infrastructure.providers.api.stats_provider import TheOddsApiStatsProvider
from src.infrastructure.providers.scraping.browser import PlaywrightBrowserSession
from src.infrastructure.providers.scraping.provider import PlaywrightLocalOddsProvider


@lru_cache
def get_settings() -> Settings:
    return Settings()


# --- build_*: plain-argument composition, reused by both FastAPI and the scheduler ---


def build_market_value_detector(settings: Settings) -> MarketValueDetector:
    """Devig strategy choice: Multiplicative (the industry-standard
    baseline) - Shin/Additive/Power (Phase 6) are equally valid drop-in
    swaps here if a different devig policy is ever wanted."""
    return MarketValueDetector(
        MultiplicativeDevig(),
        min_ev_threshold=settings.min_ev_threshold,
        kelly_fraction=settings.kelly_fraction,
    )


def build_match_value_detector(settings: Settings) -> MatchValueDetector:
    # Concrete xG model - the ONE line a trained MatchStatisticalModel
    # (Prompt 10) replaces. Everything else (MatchValueDetector, the use
    # case that calls it) depends on the MatchStatisticalModel interface,
    # not on DixonColesModel, and needs no change when this line does.
    statistical_model = DixonColesModel()
    return MatchValueDetector(
        statistical_model,
        build_market_value_detector(settings),
        min_ev_threshold=settings.min_ev_threshold,
        kelly_fraction=settings.kelly_fraction,
        mode=ConfirmationMode(settings.match_confirmation_mode),
        market_weight=settings.market_weight,
    )


def build_player_prop_detector(settings: Settings) -> PlayerPropDetector:
    # Concrete props model - the ONE line a trained PlayerPropsModel
    # (Prompt 10) replaces; PlayerPropDetector depends on the
    # PlayerPropsModel interface, not on PoissonPropsModel.
    model = PoissonPropsModel()
    return PlayerPropDetector(
        model, min_ev_threshold=settings.min_ev_threshold, kelly_fraction=settings.kelly_fraction
    )


def build_run_pipeline_use_case(
    session: AsyncSession, settings: Settings, local_odds_provider: LocalOddsProvider
) -> RunPipelineUseCase:
    match_repository = SqlAlchemyMatchRepository(session)
    odds_repository = SqlAlchemyOddsRepository(session)
    player_repository = SqlAlchemyPlayerRepository(session)
    player_stats_repository = SqlAlchemyPlayerStatsRepository(session)
    value_bet_repository = SqlAlchemyValueBetRepository(session)

    odds_api_client = TheOddsApiClient.from_settings(settings)
    sportmonks_client = SportmonksClient.from_settings(settings)

    ingest_sharp_odds = IngestSharpOddsUseCase(
        sharp_odds_provider=TheOddsApiSharpOddsProvider(odds_api_client, settings.sport_key),
        stats_provider=TheOddsApiStatsProvider(odds_api_client, settings.sport_key),
        match_repository=match_repository,
        odds_repository=odds_repository,
    )
    ingest_local_odds = IngestLocalOddsUseCase(
        local_odds_provider=local_odds_provider, odds_repository=odds_repository
    )
    ingest_player_stats = IngestPlayerStatsUseCase(
        player_stats_provider=SportmonksPlayerStatsProvider(sportmonks_client),
        player_repository=player_repository,
        player_stats_repository=player_stats_repository,
    )
    detect_match_value_bets = DetectMatchValueBetsUseCase(
        match_value_detector=build_match_value_detector(settings),
        value_bet_repository=value_bet_repository,
        league_average_goals=settings.league_average_goals,
    )
    detect_player_prop_value_bets = DetectPlayerPropValueBetsUseCase(
        player_prop_detector=build_player_prop_detector(settings),
        value_bet_repository=value_bet_repository,
    )

    return RunPipelineUseCase(
        match_repository=match_repository,
        ingest_sharp_odds=ingest_sharp_odds,
        ingest_local_odds=ingest_local_odds,
        ingest_player_stats=ingest_player_stats,
        detect_match_value_bets=detect_match_value_bets,
        detect_player_prop_value_bets=detect_player_prop_value_bets,
    )


# --- get_*: thin FastAPI Depends() adapters over the build_* functions --------


async def get_local_odds_provider(
    settings: Settings = Depends(get_settings),
) -> AsyncGenerator[LocalOddsProvider, None]:
    """One headless browser session per request that needs it, closed
    afterwards - not held open for the app's lifetime."""
    async with PlaywrightBrowserSession() as browser_session:
        yield PlaywrightLocalOddsProvider(browser_session, settings.local_bookmaker)


async def get_run_pipeline_use_case(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    local_odds_provider: LocalOddsProvider = Depends(get_local_odds_provider),
) -> RunPipelineUseCase:
    return build_run_pipeline_use_case(session, settings, local_odds_provider)


async def get_list_value_bets_use_case(
    session: AsyncSession = Depends(get_session),
) -> ListValueBetsUseCase:
    return ListValueBetsUseCase(value_bet_repository=SqlAlchemyValueBetRepository(session))


async def get_match_repository(session: AsyncSession = Depends(get_session)) -> MatchRepository:
    """Standalone, beyond what `build_run_pipeline_use_case` wires
    internally - `/value-bets/query` needs to resolve a match_id to a
    `Match` before it can run the pipeline for just that one match."""
    return SqlAlchemyMatchRepository(session)
