"""Low-level HTTP client for The Odds API v4.

Owns endpoint construction, authentication (the `apiKey` query param),
connection pooling/timeouts, and 429/5xx retry-with-backoff. Returns
validated DTOs (dtos.py) - callers never see raw JSON, a pydantic
ValidationError, or an httpx exception.
"""

from types import TracebackType
from typing import Any, Self

import httpx
from pydantic import TypeAdapter, ValidationError
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.infrastructure.config import Settings
from src.infrastructure.providers.api.dtos import EventOddsDTO, ScoreEventDTO
from src.infrastructure.providers.exceptions import ProviderUnavailableError, RateLimitError

_EVENT_ODDS_LIST_ADAPTER = TypeAdapter(list[EventOddsDTO])
_SCORE_EVENT_LIST_ADAPTER = TypeAdapter(list[ScoreEventDTO])


class _RetryableStatusError(Exception):
    """Internal signal for tenacity: this response should be retried.
    Never escapes this module."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        super().__init__(f"Retryable HTTP status {response.status_code}")


class TheOddsApiClient:
    """Thin wrapper around httpx.AsyncClient for The Odds API.

    Usable as an async context manager, or constructed/closed manually via
    `aclose()` - either way the underlying connection pool is created once
    and reused across requests.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 10.0,
        max_connections: int = 20,
        max_attempts: int = 4,
        wait_min: float = 0.5,
        wait_max: float = 8.0,
        wait_multiplier: float = 0.5,
    ) -> None:
        self._api_key = api_key
        self._http = httpx.AsyncClient(
            # Trailing slash matters: httpx joins a base_url + a *relative*
            # (no leading "/") request path per RFC 3986, so "/v4" in the
            # configured base_url survives. A leading "/" on the request
            # path would instead replace the whole base path and silently
            # drop "/v4".
            base_url=base_url.rstrip("/") + "/",
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(
                max_connections=max_connections, max_keepalive_connections=max_connections
            ),
        )
        self._retrying = AsyncRetrying(
            retry=retry_if_exception_type(_RetryableStatusError),
            wait=wait_exponential(multiplier=wait_multiplier, min=wait_min, max=wait_max),
            stop=stop_after_attempt(max_attempts),
            reraise=True,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "TheOddsApiClient":
        return cls(base_url=settings.odds_api_base_url, api_key=settings.odds_api_key)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_event_odds(
        self,
        sport_key: str,
        event_id: str,
        *,
        regions: str = "eu",
        markets: str = "h2h",
        bookmakers: str | None = None,
        odds_format: str = "decimal",
    ) -> EventOddsDTO:
        raw = await self._get(
            f"sports/{sport_key}/events/{event_id}/odds",
            self._odds_params(
                regions=regions, markets=markets, bookmakers=bookmakers, odds_format=odds_format
            ),
        )
        return self._validate(EventOddsDTO.model_validate, raw)

    async def list_odds(
        self,
        sport_key: str,
        *,
        regions: str = "eu",
        markets: str = "h2h",
        bookmakers: str | None = None,
        odds_format: str = "decimal",
    ) -> list[EventOddsDTO]:
        raw = await self._get(
            f"sports/{sport_key}/odds",
            self._odds_params(
                regions=regions, markets=markets, bookmakers=bookmakers, odds_format=odds_format
            ),
        )
        return self._validate(_EVENT_ODDS_LIST_ADAPTER.validate_python, raw)

    async def list_scores(self, sport_key: str, *, days_from: int = 3) -> list[ScoreEventDTO]:
        raw = await self._get(f"sports/{sport_key}/scores", {"daysFrom": str(days_from)})
        return self._validate(_SCORE_EVENT_LIST_ADAPTER.validate_python, raw)

    @staticmethod
    def _odds_params(
        *, regions: str, markets: str, bookmakers: str | None, odds_format: str
    ) -> dict[str, str]:
        params = {"regions": regions, "markets": markets, "oddsFormat": odds_format}
        if bookmakers:
            params["bookmakers"] = bookmakers
        return params

    @staticmethod
    def _validate(validator: Any, raw: Any) -> Any:
        try:
            return validator(raw)
        except ValidationError as exc:
            raise ProviderUnavailableError(
                f"The Odds API returned a response that doesn't match the expected shape: {exc}"
            ) from exc

    async def _get(self, path: str, params: dict[str, str]) -> Any:
        try:
            response = await self._retrying(self._raw_get, path, params)
        except _RetryableStatusError as exc:
            status = exc.response.status_code
            if status == 429:
                retry_after = exc.response.headers.get("Retry-After")
                raise RateLimitError(
                    f"The Odds API rate limit exceeded (HTTP {status})",
                    retry_after=float(retry_after) if retry_after else None,
                ) from exc
            raise ProviderUnavailableError(f"The Odds API server error (HTTP {status})") from exc

        try:
            return response.json()
        except ValueError as exc:  # json.JSONDecodeError is a ValueError subclass
            raise ProviderUnavailableError(f"The Odds API returned invalid JSON: {exc}") from exc

    async def _raw_get(self, path: str, params: dict[str, str]) -> httpx.Response:
        query = {**params, "apiKey": self._api_key}
        try:
            response = await self._http.get(path, params=query)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"The Odds API request failed: {exc}") from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise _RetryableStatusError(response)
        if response.status_code >= 400:
            raise ProviderUnavailableError(
                f"The Odds API returned an unexpected client error (HTTP {response.status_code})"
            )
        return response
