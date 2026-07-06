"""Scheduler wiring tests.

`run_scheduled_pipeline` opens its own DB session (via the real
`get_session_factory()`, pointed at an in-memory SQLite through
`test_settings`/monkeypatched `Settings()`) and its own Playwright browser
session - the latter is monkeypatched to a fake so no browser launches.
"""

from unittest.mock import AsyncMock, patch

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.infrastructure.config import Settings
from src.infrastructure.persistence import session as session_module
from src.presentation.api.scheduler import create_scheduler, run_scheduled_pipeline


@pytest.fixture(autouse=True)
def _reset_session_factory():
    yield
    session_module._engine = None
    session_module._session_factory = None


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        ODDS_API_KEY="test-key",
        SPORTMONKS_API_TOKEN="test-token",
        PIPELINE_INTERVAL_SECONDS=120,
    )


def test_create_scheduler_registers_the_pipeline_job_with_the_configured_interval(
    test_settings: Settings,
) -> None:
    # create_scheduler() only registers the job; it never starts the
    # scheduler (app.py's lifespan does that) - nothing to shut down here.
    scheduler = create_scheduler(test_settings)

    assert isinstance(scheduler, AsyncIOScheduler)
    job = scheduler.get_job("ev_betting_pipeline")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 120


async def test_run_scheduled_pipeline_executes_and_logs_the_result(test_settings: Settings) -> None:
    from src.application.use_cases.run_pipeline import PipelineRunResult

    fake_result = PipelineRunResult(matches_processed=0, match_value_bets=[], player_prop_value_bets=[])
    fake_use_case = AsyncMock()
    fake_use_case.execute.return_value = fake_result

    with (
        patch("src.presentation.api.scheduler.PlaywrightBrowserSession") as fake_browser_session_cls,
        patch(
            "src.presentation.api.scheduler.build_run_pipeline_use_case", return_value=fake_use_case
        ),
    ):
        fake_browser_session_cls.return_value.__aenter__.return_value = object()
        fake_browser_session_cls.return_value.__aexit__.return_value = False

        await run_scheduled_pipeline(test_settings)

    fake_use_case.execute.assert_awaited_once()


async def test_run_scheduled_pipeline_logs_and_reraises_on_failure(test_settings: Settings) -> None:
    fake_use_case = AsyncMock()
    fake_use_case.execute.side_effect = RuntimeError("boom")

    with (
        patch("src.presentation.api.scheduler.PlaywrightBrowserSession") as fake_browser_session_cls,
        patch(
            "src.presentation.api.scheduler.build_run_pipeline_use_case", return_value=fake_use_case
        ),
    ):
        fake_browser_session_cls.return_value.__aenter__.return_value = object()
        fake_browser_session_cls.return_value.__aexit__.return_value = False

        with pytest.raises(RuntimeError, match="boom"):
            await run_scheduled_pipeline(test_settings)
