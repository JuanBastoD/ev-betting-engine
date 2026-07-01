from typing import Any

import httpx
import pytest
import respx

from src.infrastructure.config import Settings
from src.infrastructure.providers.api.player_stats.client import SportmonksClient
from src.infrastructure.providers.exceptions import ProviderUnavailableError, RateLimitError

BASE_URL = "https://api.sportmonks.com/v3/football"


def _fast_client(**overrides: object) -> SportmonksClient:
    params: dict[str, object] = {
        "base_url": BASE_URL,
        "api_token": "test-token",
        "max_attempts": 3,
        "wait_min": 0.0,
        "wait_max": 0.01,
        "wait_multiplier": 0.001,
    }
    params.update(overrides)
    return SportmonksClient(**params)  # type: ignore[arg-type]


async def test_get_player_recent_matches_hits_the_versioned_url_with_api_token_and_per_page(
    player_recent_matches_json: dict[str, Any],
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/players/1100/latest").mock(
            return_value=httpx.Response(200, json=player_recent_matches_json)
        )

        client = _fast_client()
        try:
            entries = await client.get_player_recent_matches("1100", last=3)
        finally:
            await client.aclose()

        assert len(entries) == 3
        request = route.calls.last.request
        assert request.url.params["api_token"] == "test-token"
        assert request.url.params["per_page"] == "3"


async def test_get_injury_report_parses_a_realistic_payload(injuries_json: dict[str, Any]) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/injuries").mock(
            return_value=httpx.Response(200, json=injuries_json)
        )

        client = _fast_client()
        try:
            entries = await client.get_injury_report("fx-3001")
        finally:
            await client.aclose()

        assert len(entries) == 3
        assert route.calls.last.request.url.params["fixture_id"] == "fx-3001"


async def test_get_fixture_lineup_parses_a_confirmed_payload(
    lineup_confirmed_json: dict[str, Any],
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/fixtures/fx-3001/lineup").mock(
            return_value=httpx.Response(200, json=lineup_confirmed_json)
        )

        client = _fast_client()
        try:
            lineup = await client.get_fixture_lineup("fx-3001")
        finally:
            await client.aclose()

        assert lineup.is_confirmed is True
        assert len(lineup.entries) == 2


async def test_get_player_recent_matches_handles_an_empty_list_response() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/players/1100/latest").mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        client = _fast_client()
        try:
            entries = await client.get_player_recent_matches("1100")
        finally:
            await client.aclose()

        assert entries == []


async def test_raises_provider_unavailable_when_data_envelope_is_missing() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/injuries").mock(
            return_value=httpx.Response(200, json={"message": "no envelope here"})
        )

        client = _fast_client()
        try:
            with pytest.raises(ProviderUnavailableError):
                await client.get_injury_report("fx-3001")
        finally:
            await client.aclose()


async def test_raises_provider_unavailable_when_an_item_is_missing_required_fields() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/injuries").mock(
            return_value=httpx.Response(200, json={"data": [{"player_id": "p1"}]})
        )

        client = _fast_client()
        try:
            with pytest.raises(ProviderUnavailableError):
                await client.get_injury_report("fx-3001")
        finally:
            await client.aclose()


async def test_raises_provider_unavailable_for_a_non_json_body() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/injuries").mock(return_value=httpx.Response(200, text="not json"))

        client = _fast_client()
        try:
            with pytest.raises(ProviderUnavailableError):
                await client.get_injury_report("fx-3001")
        finally:
            await client.aclose()


async def test_retries_on_429_and_succeeds_on_a_later_attempt(
    injuries_json: dict[str, Any],
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/injuries")
        route.side_effect = [
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json=injuries_json),
        ]

        client = _fast_client()
        try:
            entries = await client.get_injury_report("fx-3001")
        finally:
            await client.aclose()

        assert len(entries) == 3
        assert route.call_count == 2


async def test_429_exhausts_retries_and_raises_rate_limit_error_with_retry_after() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/injuries").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "2.5"})
        )

        client = _fast_client(max_attempts=3)
        try:
            with pytest.raises(RateLimitError) as exc_info:
                await client.get_injury_report("fx-3001")
        finally:
            await client.aclose()

        assert exc_info.value.retry_after == 2.5
        assert route.call_count == 3


async def test_5xx_exhausts_retries_and_raises_provider_unavailable_error() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/injuries").mock(return_value=httpx.Response(503))

        client = _fast_client(max_attempts=3)
        try:
            with pytest.raises(ProviderUnavailableError):
                await client.get_injury_report("fx-3001")
        finally:
            await client.aclose()

        assert route.call_count == 3


async def test_5xx_retries_and_succeeds_on_a_later_attempt(injuries_json: dict[str, Any]) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/injuries")
        route.side_effect = [
            httpx.Response(500),
            httpx.Response(502),
            httpx.Response(200, json=injuries_json),
        ]

        client = _fast_client(max_attempts=3)
        try:
            entries = await client.get_injury_report("fx-3001")
        finally:
            await client.aclose()

        assert len(entries) == 3
        assert route.call_count == 3


async def test_a_non_429_non_5xx_client_error_is_not_retried() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/fixtures/missing-fixture/lineup").mock(
            return_value=httpx.Response(404)
        )

        client = _fast_client()
        try:
            with pytest.raises(ProviderUnavailableError):
                await client.get_fixture_lineup("missing-fixture")
        finally:
            await client.aclose()

        assert route.call_count == 1


async def test_a_network_error_is_not_retried_and_becomes_provider_unavailable() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/injuries").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        client = _fast_client()
        try:
            with pytest.raises(ProviderUnavailableError):
                await client.get_injury_report("fx-3001")
        finally:
            await client.aclose()

        assert route.call_count == 1


async def test_client_is_usable_as_an_async_context_manager(injuries_json: dict[str, Any]) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/injuries").mock(return_value=httpx.Response(200, json=injuries_json))

        async with _fast_client() as client:
            entries = await client.get_injury_report("fx-3001")

        assert len(entries) == 3


async def test_from_settings_wires_base_url_and_api_token_from_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, injuries_json: dict[str, Any]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ODDS_API_KEY", "unused-in-this-test")
    monkeypatch.setenv("SPORTMONKS_API_TOKEN", "secret-from-settings")
    monkeypatch.setenv("SPORTMONKS_BASE_URL", "https://mock.sportmonks.local/v3/football")

    with respx.mock(assert_all_called=True) as router:
        route = router.get("https://mock.sportmonks.local/v3/football/injuries").mock(
            return_value=httpx.Response(200, json=injuries_json)
        )

        client = SportmonksClient.from_settings(Settings())
        try:
            await client.get_injury_report("fx-3001")
        finally:
            await client.aclose()

        assert route.calls.last.request.url.params["api_token"] == "secret-from-settings"
