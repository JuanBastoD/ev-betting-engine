from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
import respx

from src.domain.entities.league import League
from src.domain.entities.match import Match
from src.domain.entities.team import Team
from src.domain.ports.sharp_odds_provider import SharpOddsProvider
from src.infrastructure.providers.api.client import TheOddsApiClient
from src.infrastructure.providers.api.sharp_odds_provider import TheOddsApiSharpOddsProvider
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


def _match(match_id: str) -> Match:
    return Match(
        id=match_id,
        home_team=Team(id="manchester-united", name="Manchester United"),
        away_team=Team(id="liverpool", name="Liverpool"),
        league=League(id="soccer_epl", name="EPL"),
        kickoff_utc=datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc),
    )


async def test_the_odds_api_sharp_odds_provider_satisfies_the_domain_port() -> None:
    client = _fast_client()
    try:
        provider = TheOddsApiSharpOddsProvider(client, sport_key="soccer_epl")
        assert isinstance(provider, SharpOddsProvider)
    finally:
        await client.aclose()


async def test_get_odds_returns_pinnacle_1x2_quotes_for_a_single_match(
    single_event_odds_json: dict[str, Any],
) -> None:
    match = _match("e912304de1234567890abcdef123456")

    with respx.mock(assert_all_called=True) as router:
        router.get(
            f"{BASE_URL}/sports/soccer_epl/events/{match.id}/odds"
        ).mock(return_value=httpx.Response(200, json=single_event_odds_json))

        client = _fast_client()
        try:
            provider = TheOddsApiSharpOddsProvider(client, sport_key="soccer_epl")
            quotes = await provider.get_odds(match)
        finally:
            await client.aclose()

    assert len(quotes) == 3
    assert all(quote.bookmaker.is_sharp for quote in quotes)
    by_outcome = {quote.selection.outcome: quote.odds.value for quote in quotes}
    assert by_outcome == {"Home": 2.10, "Away": 3.40, "Draw": 3.25}


async def test_get_sharp_1x2_odds_for_matches_filters_to_the_requested_matches(
    event_odds_list_json: list[dict[str, Any]],
) -> None:
    wanted_match = _match("e912304de1234567890abcdef123456")
    not_in_response_match = _match("does-not-exist-in-response")

    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/sports/soccer_epl/odds").mock(
            return_value=httpx.Response(200, json=event_odds_list_json)
        )

        client = _fast_client()
        try:
            provider = TheOddsApiSharpOddsProvider(client, sport_key="soccer_epl")
            result = await provider.get_sharp_1x2_odds_for_matches(
                [wanted_match, not_in_response_match]
            )
        finally:
            await client.aclose()

    # One API call regardless of how many matches were requested.
    assert route.call_count == 1
    assert set(result.keys()) == {"e912304de1234567890abcdef123456"}
    assert len(result["e912304de1234567890abcdef123456"]) == 3


async def test_get_sharp_1x2_odds_for_matches_returns_empty_dict_for_empty_response() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/sports/soccer_epl/odds").mock(
            return_value=httpx.Response(200, json=[])
        )

        client = _fast_client()
        try:
            provider = TheOddsApiSharpOddsProvider(client, sport_key="soccer_epl")
            result = await provider.get_sharp_1x2_odds_for_matches([_match("anything")])
        finally:
            await client.aclose()

    assert result == {}


async def test_get_odds_propagates_provider_unavailable_error() -> None:
    match = _match("broken-event")

    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/sports/soccer_epl/events/{match.id}/odds").mock(
            return_value=httpx.Response(503)
        )

        client = _fast_client()
        try:
            provider = TheOddsApiSharpOddsProvider(client, sport_key="soccer_epl")
            with pytest.raises(ProviderUnavailableError):
                await provider.get_odds(match)
        finally:
            await client.aclose()


async def test_get_sharp_1x2_odds_for_matches_propagates_rate_limit_error() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/sports/soccer_epl/odds").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "3"})
        )

        client = _fast_client()
        try:
            provider = TheOddsApiSharpOddsProvider(client, sport_key="soccer_epl")
            with pytest.raises(RateLimitError) as exc_info:
                await provider.get_sharp_1x2_odds_for_matches([_match("anything")])
        finally:
            await client.aclose()

    assert exc_info.value.retry_after == 3.0
