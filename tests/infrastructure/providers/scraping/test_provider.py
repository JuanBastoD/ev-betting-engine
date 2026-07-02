from collections.abc import Callable

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.domain.entities.match import Match
from src.domain.ports.local_odds_provider import LocalOddsProvider
from src.infrastructure.providers.scraping.betplay import BetplayScraper
from src.infrastructure.providers.scraping.exceptions import SelectorNotFoundError
from src.infrastructure.providers.scraping.provider import PlaywrightLocalOddsProvider
from tests.infrastructure.providers.scraping.fakes import FakeBrowserSession, FakePage

FAST_RETRIES = {
    "request_delay_seconds": 0.0,
    "max_attempts": 3,
    "wait_min": 0.0,
    "wait_max": 0.001,
    "wait_multiplier": 0.0001,
}


def make_provider(page: FakePage, bookmaker_name: str = "Betplay") -> PlaywrightLocalOddsProvider:
    return PlaywrightLocalOddsProvider(FakeBrowserSession(page), bookmaker_name, **FAST_RETRIES)


def betplay_page(load_fixture: Callable[[str], str]) -> FakePage:
    return FakePage(
        html_by_selector={
            BetplayScraper.match_odds_container_selector: load_fixture("betplay_match_odds.html"),
            BetplayScraper.props_container_selector: load_fixture("betplay_player_props.html"),
        }
    )


def test_provider_satisfies_the_domain_port() -> None:
    assert isinstance(make_provider(FakePage()), LocalOddsProvider)


async def test_get_odds_navigates_scrapes_and_closes_the_page(
    match: Match, load_fixture: Callable[[str], str]
) -> None:
    page = betplay_page(load_fixture)

    quotes = await make_provider(page).get_odds(match)

    assert len(quotes) == 7
    assert page.goto_calls == [
        "https://betplay.com.co/apuestas/futbol/junior-fc-vs-america-de-cali"
    ]
    assert page.closed is True


async def test_get_player_props_opens_the_players_tab_and_closes_the_page(
    match: Match, load_fixture: Callable[[str], str]
) -> None:
    page = betplay_page(load_fixture)

    props = await make_provider(page).get_player_props(match)

    assert len(props) == 4
    assert page.click_calls == [BetplayScraper.props_tab_selector]
    assert page.closed is True


async def test_scraper_kwargs_are_forwarded_to_the_scraper(
    match: Match, load_fixture: Callable[[str], str]
) -> None:
    page = betplay_page(load_fixture)
    provider = PlaywrightLocalOddsProvider(
        FakeBrowserSession(page), "Betplay", base_url="https://mirror.betplay.test", **FAST_RETRIES
    )

    await provider.get_odds(match)

    assert page.goto_calls[0].startswith("https://mirror.betplay.test/")


async def test_the_page_is_closed_even_when_scraping_fails(match: Match) -> None:
    page = FakePage()
    page.wait_failures = {
        BetplayScraper.match_page_ready_selector: [PlaywrightTimeoutError("timeout")] * 3
    }

    with pytest.raises(SelectorNotFoundError):
        await make_provider(page).get_odds(match)
    assert page.closed is True


async def test_the_page_is_closed_even_for_unknown_bookmakers(match: Match) -> None:
    page = FakePage()

    with pytest.raises(ValueError):
        await make_provider(page, bookmaker_name="Wplay").get_odds(match)
    assert page.closed is True
