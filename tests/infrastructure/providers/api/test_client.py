from typing import Any

import httpx
import pytest
import respx

from src.infrastructure.config import Settings
from src.infrastructure.providers.api.client import TheOddsApiClient
from src.infrastructure.providers.exceptions import ProviderUnavailableError, RateLimitError

BASE_URL = "https://api.the-odds-api.com/v4"


def _fast_client(**overrides: object) -> TheOddsApiClient:
    """A client configured for near-instant retries, so tests exercising
    429/5xx backoff don't actually sleep for seconds."""
    params: dict[str, object] = {
        "base_url": BASE_URL,
        "api_key": "test-key",
        "max_attempts": 3,
        "wait_min": 0.0,
        "wait_max": 0.01,
        "wait_multiplier": 0.001,
    }
    params.update(overrides)
    return TheOddsApiClient(**params)  # type: ignore[arg-type]


async def test_get_event_odds_hits_the_versioned_url_with_api_key_and_query_params(
    single_event_odds_json: dict[str, Any],
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(
            f"{BASE_URL}/sports/soccer_epl/events/e912304de1234567890abcdef123456/odds"
        ).mock(return_value=httpx.Response(200, json=single_event_odds_json))

        client = _fast_client()
        try:
            event = await client.get_event_odds(
                "soccer_epl", "e912304de1234567890abcdef123456", bookmakers="pinnacle"
            )
        finally:
            await client.aclose()

        assert event.id == "e912304de1234567890abcdef123456"
        request = route.calls.last.request
        assert request.url.params["apiKey"] == "test-key"
        assert request.url.params["bookmakers"] == "pinnacle"
        assert request.url.params["markets"] == "h2h"


async def test_list_odds_parses_a_realistic_multi_event_payload(
    event_odds_list_json: list[dict[str, Any]],
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/sports/soccer_epl/odds").mock(
            return_value=httpx.Response(200, json=event_odds_list_json)
        )

        client = _fast_client()
        try:
            events = await client.list_odds("soccer_epl")
        finally:
            await client.aclose()

        assert [event.id for event in events] == [
            "e912304de1234567890abcdef123456",
            "f823415ef2345678901bcdef2345678",
        ]


async def test_list_scores_parses_a_realistic_payload_and_passes_days_from(
    scores_list_json: list[dict[str, Any]],
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/sports/soccer_epl/scores").mock(
            return_value=httpx.Response(200, json=scores_list_json)
        )

        client = _fast_client()
        try:
            events = await client.list_scores("soccer_epl", days_from=10)
        finally:
            await client.aclose()

        assert len(events) == 6
        assert route.calls.last.request.url.params["daysFrom"] == "10"


async def test_list_odds_handles_an_empty_list_response() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/sports/soccer_epl/odds").mock(
            return_value=httpx.Response(200, json=[])
        )

        client = _fast_client()
        try:
            events = await client.list_odds("soccer_epl")
        finally:
            await client.aclose()

        assert events == []


async def test_list_odds_raises_provider_unavailable_for_a_non_list_payload() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/sports/soccer_epl/odds").mock(
            return_value=httpx.Response(200, json={"message": "unexpected shape"})
        )

        client = _fast_client()
        try:
            with pytest.raises(ProviderUnavailableError):
                await client.list_odds("soccer_epl")
        finally:
            await client.aclose()


async def test_list_odds_raises_provider_unavailable_when_an_item_is_missing_required_fields() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/sports/soccer_epl/odds").mock(
            return_value=httpx.Response(200, json=[{"sport_key": "soccer_epl"}])
        )

        client = _fast_client()
        try:
            with pytest.raises(ProviderUnavailableError):
                await client.list_odds("soccer_epl")
        finally:
            await client.aclose()


async def test_list_odds_raises_provider_unavailable_for_a_non_json_body() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/sports/soccer_epl/odds").mock(
            return_value=httpx.Response(200, text="not json")
        )

        client = _fast_client()
        try:
            with pytest.raises(ProviderUnavailableError):
                await client.list_odds("soccer_epl")
        finally:
            await client.aclose()


async def test_retries_on_429_and_succeeds_on_a_later_attempt(
    event_odds_list_json: list[dict[str, Any]],
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/sports/soccer_epl/odds")
        route.side_effect = [
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json=event_odds_list_json),
        ]

        client = _fast_client()
        try:
            events = await client.list_odds("soccer_epl")
        finally:
            await client.aclose()

        assert len(events) == 2
        assert route.call_count == 2


async def test_429_exhausts_retries_and_raises_rate_limit_error_with_retry_after() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/sports/soccer_epl/odds").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "2.5"})
        )

        client = _fast_client(max_attempts=3)
        try:
            with pytest.raises(RateLimitError) as exc_info:
                await client.list_odds("soccer_epl")
        finally:
            await client.aclose()

        assert exc_info.value.retry_after == 2.5
        assert route.call_count == 3


async def test_500_exhausts_retries_and_raises_provider_unavailable_error() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/sports/soccer_epl/odds").mock(
            return_value=httpx.Response(503)
        )

        client = _fast_client(max_attempts=3)
        try:
            with pytest.raises(ProviderUnavailableError):
                await client.list_odds("soccer_epl")
        finally:
            await client.aclose()

        assert route.call_count == 3


async def test_5xx_retries_and_succeeds_on_a_later_attempt(
    event_odds_list_json: list[dict[str, Any]],
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/sports/soccer_epl/odds")
        route.side_effect = [
            httpx.Response(500),
            httpx.Response(502),
            httpx.Response(200, json=event_odds_list_json),
        ]

        client = _fast_client(max_attempts=3)
        try:
            events = await client.list_odds("soccer_epl")
        finally:
            await client.aclose()

        assert len(events) == 2
        assert route.call_count == 3


async def test_a_non_429_non_5xx_client_error_is_not_retried() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(
            f"{BASE_URL}/sports/soccer_epl/events/missing-event/odds"
        ).mock(return_value=httpx.Response(404))

        client = _fast_client()
        try:
            with pytest.raises(ProviderUnavailableError):
                await client.get_event_odds("soccer_epl", "missing-event")
        finally:
            await client.aclose()

        assert route.call_count == 1


async def test_a_network_error_is_not_retried_and_becomes_provider_unavailable() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/sports/soccer_epl/odds").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        client = _fast_client()
        try:
            with pytest.raises(ProviderUnavailableError):
                await client.list_odds("soccer_epl")
        finally:
            await client.aclose()

        assert route.call_count == 1


async def test_client_is_usable_as_an_async_context_manager(
    event_odds_list_json: list[dict[str, Any]],
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/sports/soccer_epl/odds").mock(
            return_value=httpx.Response(200, json=event_odds_list_json)
        )

        async with _fast_client() as client:
            events = await client.list_odds("soccer_epl")

        assert len(events) == 2


async def test_from_settings_wires_base_url_and_api_key_from_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, event_odds_list_json: list[dict[str, Any]]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ODDS_API_KEY", "secret-from-settings")
    monkeypatch.setenv("ODDS_API_BASE_URL", "https://mock.local/v4")
    monkeypatch.setenv("SPORTMONKS_API_TOKEN", "unused-in-this-test")

    with respx.mock(assert_all_called=True) as router:
        route = router.get("https://mock.local/v4/sports/soccer_epl/odds").mock(
            return_value=httpx.Response(200, json=event_odds_list_json)
        )

        client = TheOddsApiClient.from_settings(Settings())
        try:
            await client.list_odds("soccer_epl")
        finally:
            await client.aclose()

        assert route.calls.last.request.url.params["apiKey"] == "secret-from-settings"
