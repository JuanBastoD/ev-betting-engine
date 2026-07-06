"""Translates domain/application/provider exceptions into HTTP responses.

Registered once on the app (`app.py`) rather than scattered per-route -
every route can just let these propagate instead of catching them locally.
"""

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.application.exceptions import (
    MatchNotFoundError,
    PlayerPropNotFoundError,
    ValueBetNotFoundError,
)
from src.infrastructure.providers.exceptions import ProviderError

logger = structlog.get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(MatchNotFoundError)
    @app.exception_handler(PlayerPropNotFoundError)
    @app.exception_handler(ValueBetNotFoundError)
    async def _handle_not_found(request: Request, exc: Exception) -> JSONResponse:
        logger.info("not_found", path=request.url.path, error=str(exc))
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
        # Domain entities/services validate their own invariants and
        # business rules by raising plain ValueError (no domain-specific
        # exception hierarchy) - a caller-facing request that trips one of
        # these is a bad request, not a server fault.
        logger.info("bad_request", path=request.url.path, error=str(exc))
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(ProviderError)
    async def _handle_provider_error(request: Request, exc: ProviderError) -> JSONResponse:
        # An upstream data source (odds/stats API, local bookmaker scrape)
        # failed or is rate-limited - the server did nothing wrong, but it
        # can't complete the request either.
        logger.warning("upstream_provider_error", path=request.url.path, error=str(exc))
        return JSONResponse(status_code=502, content={"detail": f"Upstream provider error: {exc}"})

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_exception", path=request.url.path, error=str(exc), exc_info=exc
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
