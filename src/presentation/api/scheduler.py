"""APScheduler (AsyncIOScheduler) wiring: runs the same pipeline the
`POST /pipeline/run` endpoint does, on a periodic interval read from
`Settings.pipeline_interval_seconds`.

Calls `build_run_pipeline_use_case` directly (the same composition-root
function the API route depends on via `Depends()`) rather than duplicating
the wiring - see `dependencies.py`'s module docstring for why this needs a
plain function call here instead of `Depends()`, which only resolves
inside a FastAPI request.
"""

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.infrastructure.config import Settings
from src.infrastructure.persistence.session import get_session_factory
from src.infrastructure.providers.scraping.browser import PlaywrightBrowserSession
from src.infrastructure.providers.scraping.provider import PlaywrightLocalOddsProvider
from src.presentation.api.dependencies import build_run_pipeline_use_case

logger = structlog.get_logger(__name__)


async def run_scheduled_pipeline(settings: Settings) -> None:
    """One full pipeline pass: its own DB session and browser session,
    each opened and closed around this single run - nothing is held open
    between scheduled ticks."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        async with PlaywrightBrowserSession() as browser_session:
            local_odds_provider = PlaywrightLocalOddsProvider(
                browser_session, settings.local_bookmaker
            )
            use_case = build_run_pipeline_use_case(session, settings, local_odds_provider)
            try:
                result = await use_case.execute()
            except Exception:
                logger.error("scheduled_pipeline_failed", exc_info=True)
                raise
            logger.info(
                "scheduled_pipeline_completed",
                matches_processed=result.matches_processed,
                match_value_bets=len(result.match_value_bets),
                player_prop_value_bets=len(result.player_prop_value_bets),
            )


def create_scheduler(settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_scheduled_pipeline,
        "interval",
        seconds=settings.pipeline_interval_seconds,
        args=[settings],
        id="ev_betting_pipeline",
        replace_existing=True,
    )
    return scheduler
