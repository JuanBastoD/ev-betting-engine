"""Exception-handler tests, in isolation from any real route: a throwaway
FastAPI app with `register_exception_handlers` applied and one route per
exception type, deliberately raising it - decouples "does the handler
translate this exception to the right HTTP status" from needing a natural
business scenario for every exception type (some, like a raw
`ProviderUnavailableError`, aren't easy to trigger through a real route
without live external services).
"""

from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from src.application.exceptions import MatchNotFoundError, PlayerPropNotFoundError
from src.infrastructure.providers.exceptions import ProviderUnavailableError, RateLimitError
from src.presentation.api.exception_handlers import register_exception_handlers


def _build_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise/match-not-found")
    async def _raise_match_not_found() -> None:
        raise MatchNotFoundError("match-1")

    @app.get("/raise/player-prop-not-found")
    async def _raise_player_prop_not_found() -> None:
        raise PlayerPropNotFoundError("match-1", "Lionel Messi")

    @app.get("/raise/value-error")
    async def _raise_value_error() -> None:
        raise ValueError("line must be positive")

    @app.get("/raise/provider-unavailable")
    async def _raise_provider_unavailable() -> None:
        raise ProviderUnavailableError("odds API returned 503")

    @app.get("/raise/rate-limit")
    async def _raise_rate_limit() -> None:
        raise RateLimitError("rate limited", retry_after=4.0)

    @app.get("/raise/unexpected")
    async def _raise_unexpected() -> None:
        raise RuntimeError("something truly unexpected")

    return app


@pytest_asyncio.fixture
async def test_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    # raise_app_exceptions=False: the generic Exception handler already
    # translates an unhandled error into a 500 JSONResponse - by default
    # the ASGI transport re-raises it anyway (for debugging convenience),
    # which would fail this specific test rather than let it assert on the
    # response the handler actually produced.
    transport = httpx.ASGITransport(app=_build_test_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_match_not_found_returns_404(test_client: httpx.AsyncClient) -> None:
    response = await test_client.get("/raise/match-not-found")

    assert response.status_code == 404
    assert "match-1" in response.json()["detail"]


async def test_player_prop_not_found_returns_404(test_client: httpx.AsyncClient) -> None:
    response = await test_client.get("/raise/player-prop-not-found")

    assert response.status_code == 404
    assert "Lionel Messi" in response.json()["detail"]


async def test_value_error_returns_400(test_client: httpx.AsyncClient) -> None:
    response = await test_client.get("/raise/value-error")

    assert response.status_code == 400
    assert response.json()["detail"] == "line must be positive"


async def test_provider_unavailable_returns_502(test_client: httpx.AsyncClient) -> None:
    response = await test_client.get("/raise/provider-unavailable")

    assert response.status_code == 502
    assert "odds API returned 503" in response.json()["detail"]


async def test_rate_limit_error_returns_502(test_client: httpx.AsyncClient) -> None:
    response = await test_client.get("/raise/rate-limit")

    assert response.status_code == 502


async def test_unexpected_exception_returns_500_without_leaking_details(
    test_client: httpx.AsyncClient,
) -> None:
    response = await test_client.get("/raise/unexpected")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
