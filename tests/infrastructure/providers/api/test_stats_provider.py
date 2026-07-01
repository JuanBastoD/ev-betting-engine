from typing import Any

import httpx
import pytest
import respx

from src.domain.entities.team import Team
from src.domain.ports.stats_provider import StatsProvider
from src.infrastructure.providers.api.client import TheOddsApiClient
from src.infrastructure.providers.api.stats_provider import TheOddsApiStatsProvider
from src.infrastructure.providers.exceptions import ProviderUnavailableError, RateLimitError

BASE_URL = "https://api.the-odds-api.com/v4"


def _fast_client() -> TheOddsApiClient:
    return TheOddsApiClient(
        base_url=BASE_URL,
        api_key="test-key",
        max_attempts=3,
        wait_min=0.0,
        wait_max=0.01,
        wait_multiplier=0.001,
    )


async def test_the_odds_api_stats_provider_satisfies_the_domain_port() -> None:
    client = _fast_client()
    try:
        provider = TheOddsApiStatsProvider(client, sport_key="soccer_epl")
        assert isinstance(provider, StatsProvider)
    finally:
        await client.aclose()


async def test_get_team_form_aggregates_the_teams_recent_results(
    scores_list_json: list[dict[str, Any]],
) -> None:
    team = Team(id="manchester-united", name="Manchester United")

    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/sports/soccer_epl/scores").mock(
            return_value=httpx.Response(200, json=scores_list_json)
        )

        client = _fast_client()
        try:
            provider = TheOddsApiStatsProvider(client, sport_key="soccer_epl")
            form = await provider.get_team_form(team)
        finally:
            await client.aclose()

    assert form.matches_played == 4
    assert form.wins == 2
    assert form.draws == 1
    assert form.losses == 1
    assert form.goals_for == 6
    assert form.goals_against == 4


async def test_get_team_forms_computes_every_team_from_a_single_call(
    scores_list_json: list[dict[str, Any]],
) -> None:
    manchester_united = Team(id="manchester-united", name="Manchester United")
    tottenham = Team(id="tottenham-hotspur", name="Tottenham Hotspur")

    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/sports/soccer_epl/scores").mock(
            return_value=httpx.Response(200, json=scores_list_json)
        )

        client = _fast_client()
        try:
            provider = TheOddsApiStatsProvider(client, sport_key="soccer_epl")
            forms = await provider.get_team_forms([manchester_united, tottenham])
        finally:
            await client.aclose()

    assert route.call_count == 1
    assert forms["manchester-united"].matches_played == 4
    assert forms["tottenham-hotspur"].matches_played == 0


async def test_get_team_form_returns_zeroed_form_for_an_empty_scores_response() -> None:
    team = Team(id="manchester-united", name="Manchester United")

    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/sports/soccer_epl/scores").mock(
            return_value=httpx.Response(200, json=[])
        )

        client = _fast_client()
        try:
            provider = TheOddsApiStatsProvider(client, sport_key="soccer_epl")
            form = await provider.get_team_form(team)
        finally:
            await client.aclose()

    assert form.matches_played == 0


async def test_get_team_form_propagates_provider_unavailable_error() -> None:
    team = Team(id="manchester-united", name="Manchester United")

    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/sports/soccer_epl/scores").mock(
            return_value=httpx.Response(500)
        )

        client = _fast_client()
        try:
            provider = TheOddsApiStatsProvider(client, sport_key="soccer_epl")
            with pytest.raises(ProviderUnavailableError):
                await provider.get_team_form(team)
        finally:
            await client.aclose()


async def test_get_team_forms_propagates_rate_limit_error() -> None:
    team = Team(id="manchester-united", name="Manchester United")

    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/sports/soccer_epl/scores").mock(
            return_value=httpx.Response(429)
        )

        client = _fast_client()
        try:
            provider = TheOddsApiStatsProvider(client, sport_key="soccer_epl")
            with pytest.raises(RateLimitError):
                await provider.get_team_forms([team])
        finally:
            await client.aclose()
