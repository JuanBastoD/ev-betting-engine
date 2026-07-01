from typing import Any

import httpx
import pytest
import respx

from src.domain.ports.player_stats_provider import PlayerStatsProvider
from src.infrastructure.providers.api.player_stats.client import SportmonksClient
from src.infrastructure.providers.api.player_stats.provider import SportmonksPlayerStatsProvider
from src.infrastructure.providers.exceptions import ProviderUnavailableError, RateLimitError

BASE_URL = "https://api.sportmonks.com/v3/football"


def _fast_client() -> SportmonksClient:
    return SportmonksClient(
        base_url=BASE_URL,
        api_token="test-token",
        max_attempts=3,
        wait_min=0.0,
        wait_max=0.01,
        wait_multiplier=0.001,
    )


async def test_sportmonks_player_stats_provider_satisfies_the_domain_port() -> None:
    client = _fast_client()
    try:
        provider = SportmonksPlayerStatsProvider(client)
        assert isinstance(provider, PlayerStatsProvider)
    finally:
        await client.aclose()


async def test_get_player_recent_matches_returns_mapped_stats(
    player_recent_matches_json: dict[str, Any],
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/players/1100/latest").mock(
            return_value=httpx.Response(200, json=player_recent_matches_json)
        )

        client = _fast_client()
        try:
            provider = SportmonksPlayerStatsProvider(client)
            stats = await provider.get_player_recent_matches("1100", n=3)
        finally:
            await client.aclose()

    assert len(stats) == 3
    assert stats[0].player.name == "Erling Haaland"
    assert stats[0].started is True


async def test_get_injury_report_filters_out_unrecognized_statuses(
    injuries_json: dict[str, Any],
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/injuries").mock(
            return_value=httpx.Response(200, json=injuries_json)
        )

        client = _fast_client()
        try:
            provider = SportmonksPlayerStatsProvider(client)
            statuses = await provider.get_injury_report("fx-3001")
        finally:
            await client.aclose()

    assert len(statuses) == 2
    assert {status.player.name for status in statuses} == {"Kevin De Bruyne", "John Stones"}


async def test_get_confirmed_lineup_uses_official_probabilities_when_confirmed(
    lineup_confirmed_json: dict[str, Any],
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/fixtures/fx-3001/lineup").mock(
            return_value=httpx.Response(200, json=lineup_confirmed_json)
        )

        client = _fast_client()
        try:
            provider = SportmonksPlayerStatsProvider(client)
            confirmations = await provider.get_confirmed_lineup("fx-3001")
        finally:
            await client.aclose()

    assert len(confirmations) == 2
    starting = next(c for c in confirmations if c.player.name == "Erling Haaland")
    bench = next(c for c in confirmations if c.player.name == "John Stones")
    assert starting.is_confirmed is True
    assert starting.is_starting is True
    assert starting.start_probability.value == 1.0
    assert bench.is_starting is False
    assert bench.start_probability.value == 0.0


async def test_get_confirmed_lineup_falls_back_to_historical_start_rate_when_unconfirmed(
    lineup_unconfirmed_json: dict[str, Any], player_recent_matches_json: dict[str, Any]
) -> None:
    with respx.mock(assert_all_called=True) as router:
        lineup_route = router.get(f"{BASE_URL}/fixtures/fx-3001/lineup").mock(
            return_value=httpx.Response(200, json=lineup_unconfirmed_json)
        )
        recent_matches_route = router.get(f"{BASE_URL}/players/1100/latest").mock(
            return_value=httpx.Response(200, json=player_recent_matches_json)
        )

        client = _fast_client()
        try:
            provider = SportmonksPlayerStatsProvider(client, form_window=10)
            confirmations = await provider.get_confirmed_lineup("fx-3001")
        finally:
            await client.aclose()

    assert lineup_route.call_count == 1
    assert recent_matches_route.call_count == 1
    assert len(confirmations) == 1
    confirmation = confirmations[0]
    assert confirmation.is_confirmed is False
    # 2 of the 3 fixtures in player_recent_matches_json have started=True.
    assert confirmation.start_probability.value == pytest.approx(2 / 3)
    assert confirmation.is_starting is True


async def test_get_player_recent_matches_propagates_provider_unavailable_error() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/players/1100/latest").mock(return_value=httpx.Response(503))

        client = _fast_client()
        try:
            provider = SportmonksPlayerStatsProvider(client)
            with pytest.raises(ProviderUnavailableError):
                await provider.get_player_recent_matches("1100")
        finally:
            await client.aclose()


async def test_get_injury_report_propagates_rate_limit_error() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/injuries").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "4"})
        )

        client = _fast_client()
        try:
            provider = SportmonksPlayerStatsProvider(client)
            with pytest.raises(RateLimitError) as exc_info:
                await provider.get_injury_report("fx-3001")
        finally:
            await client.aclose()

    assert exc_info.value.retry_after == 4.0


async def test_get_confirmed_lineup_propagates_error_from_the_fallback_call(
    lineup_unconfirmed_json: dict[str, Any],
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/fixtures/fx-3001/lineup").mock(
            return_value=httpx.Response(200, json=lineup_unconfirmed_json)
        )
        router.get(f"{BASE_URL}/players/1100/latest").mock(return_value=httpx.Response(500))

        client = _fast_client()
        try:
            provider = SportmonksPlayerStatsProvider(client)
            with pytest.raises(ProviderUnavailableError):
                await provider.get_confirmed_lineup("fx-3001")
        finally:
            await client.aclose()
