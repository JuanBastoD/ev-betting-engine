"""Low-level HTTP client for the Sportmonks Football API v3.

Same resilience/error-translation pattern as
src.infrastructure.providers.api.client.TheOddsApiClient (Prompt 3): tenacity
AsyncRetrying scoped to 429/5xx, everything else fails immediately as
ProviderUnavailableError, and the base_url is normalized so a versioned path
survives httpx's base_url + relative-path join. Built as a standalone class
rather than factored out into a shared base, to avoid touching the
already-shipped, already-tested odds client for this change.
"""

from typing import Any, Self
from types import TracebackType

import httpx
from pydantic import TypeAdapter, ValidationError
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.infrastructure.config import Settings
from src.infrastructure.providers.api.player_stats.dtos import (
    FixtureLineupDTO,
    InjuryEntryDTO,
    PlayerFixtureStatsDTO,
)
from src.infrastructure.providers.exceptions import ProviderUnavailableError, RateLimitError

_PLAYER_FIXTURE_STATS_LIST_ADAPTER = TypeAdapter(list[PlayerFixtureStatsDTO])
_INJURY_ENTRY_LIST_ADAPTER = TypeAdapter(list[InjuryEntryDTO])


class _RetryableStatusError(Exception):
    """Internal signal for tenacity: this response should be retried.
    Never escapes this module."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        super().__init__(f"Retryable HTTP status {response.status_code}")


class SportmonksClient:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        *,
        timeout: float = 10.0,
        max_connections: int = 20,
        max_attempts: int = 4,
        wait_min: float = 0.5,
        wait_max: float = 8.0,
        wait_multiplier: float = 0.5,
    ) -> None:
        self._api_token = api_token
        self._http = httpx.AsyncClient(
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
    def from_settings(cls, settings: Settings) -> "SportmonksClient":
        return cls(base_url=settings.sportmonks_base_url, api_token=settings.sportmonks_api_token)

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

    async def get_player_recent_matches(
        self, player_id: str, last: int = 10
    ) -> list[PlayerFixtureStatsDTO]:
        raw = await self._get(f"players/{player_id}/latest", {"per_page": str(last)})
        data = self._extract_data(raw)
        return self._validate(_PLAYER_FIXTURE_STATS_LIST_ADAPTER.validate_python, data)

    async def get_injury_report(self, fixture_id: str) -> list[InjuryEntryDTO]:
        raw = await self._get("injuries", {"fixture_id": fixture_id})
        data = self._extract_data(raw)
        return self._validate(_INJURY_ENTRY_LIST_ADAPTER.validate_python, data)

    async def get_fixture_lineup(self, fixture_id: str) -> FixtureLineupDTO:
        raw = await self._get(f"fixtures/{fixture_id}/lineup", {})
        data = self._extract_data(raw)
        return self._validate(FixtureLineupDTO.model_validate, data)

    @staticmethod
    def _extract_data(raw: Any) -> Any:
        if not isinstance(raw, dict) or "data" not in raw:
            raise ProviderUnavailableError(
                "Sportmonks response is missing the expected 'data' envelope"
            )
        return raw["data"]

    @staticmethod
    def _validate(validator: Any, raw: Any) -> Any:
        try:
            return validator(raw)
        except ValidationError as exc:
            raise ProviderUnavailableError(
                f"Sportmonks returned a response that doesn't match the expected shape: {exc}"
            ) from exc

    async def _get(self, path: str, params: dict[str, str]) -> Any:
        try:
            response = await self._retrying(self._raw_get, path, params)
        except _RetryableStatusError as exc:
            status = exc.response.status_code
            if status == 429:
                retry_after = exc.response.headers.get("Retry-After")
                raise RateLimitError(
                    f"Sportmonks rate limit exceeded (HTTP {status})",
                    retry_after=float(retry_after) if retry_after else None,
                ) from exc
            raise ProviderUnavailableError(f"Sportmonks server error (HTTP {status})") from exc

        try:
            return response.json()
        except ValueError as exc:  # json.JSONDecodeError is a ValueError subclass
            raise ProviderUnavailableError(f"Sportmonks returned invalid JSON: {exc}") from exc

    async def _raw_get(self, path: str, params: dict[str, str]) -> httpx.Response:
        query = {**params, "api_token": self._api_token}
        try:
            response = await self._http.get(path, params=query)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Sportmonks request failed: {exc}") from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise _RetryableStatusError(response)
        if response.status_code >= 400:
            raise ProviderUnavailableError(
                f"Sportmonks returned an unexpected client error (HTTP {response.status_code})"
            )
        return response
