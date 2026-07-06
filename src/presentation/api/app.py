"""FastAPI application entry point.

`uv run uvicorn src.presentation.api.app:app` serves this. The lifespan
initializes the DB connection pool and starts the scheduler on startup,
and tears both down on shutdown - nothing about request handling depends
on import-time side effects.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from src.infrastructure.persistence.session import get_session_factory, reset_session_factory
from src.presentation.api.dependencies import get_settings
from src.presentation.api.exception_handlers import register_exception_handlers
from src.presentation.api.logging_config import configure_logging
from src.presentation.api.routers import calibration, health, pipeline, value_bets
from src.presentation.api.scheduler import create_scheduler

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    settings = get_settings()

    # Eagerly create the engine/connection pool now rather than lazily on
    # the first request - get_session_factory() caches it at module level.
    get_session_factory()
    logger.info("db_pool_initialized")

    scheduler = create_scheduler(settings)
    scheduler.start()
    logger.info("scheduler_started", interval_seconds=settings.pipeline_interval_seconds)

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await reset_session_factory()
        logger.info("app_shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(title="ev-betting-engine", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(pipeline.router)
    app.include_router(value_bets.router)
    app.include_router(calibration.router)
    return app


app = create_app()
