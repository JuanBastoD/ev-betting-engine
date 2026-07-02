"""Template-method flow tests for AbstractBookmakerScraper, driven through
BetplayScraper against a FakePage - no Chromium is ever launched.

Retry-related tests construct the scraper with near-zero backoff so
exhausting attempts doesn't add real seconds to the suite.
"""

from collections.abc import Callable
from types import SimpleNamespace

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import src.infrastructure.providers.scraping.base as base_module
from src.domain.entities.match import Match
from src.infrastructure.providers.scraping.betplay import BetplayScraper
from src.infrastructure.providers.scraping.exceptions import ScrapingError, SelectorNotFoundError
from tests.infrastructure.providers.scraping.fakes import FakePage

MATCH_URL = "https://betplay.com.co/apuestas/futbol/junior-fc-vs-america-de-cali"

FAST_RETRIES = {
    "request_delay_seconds": 0.0,
    "max_attempts": 3,
    "wait_min": 0.0,
    "wait_max": 0.001,
    "wait_multiplier": 0.0001,
}


def make_scraper(page: FakePage, **overrides: object) -> BetplayScraper:
    kwargs: dict = {**FAST_RETRIES, **overrides}
    return BetplayScraper(page, **kwargs)


async def test_navigate_opens_the_match_url_and_waits_for_the_page(match: Match) -> None:
    page = FakePage()
    await make_scraper(page).navigate(match)

    assert page.goto_calls == [MATCH_URL]
    assert page.wait_calls == [BetplayScraper.match_page_ready_selector]


async def test_navigate_honors_a_custom_base_url(match: Match) -> None:
    page = FakePage()
    await make_scraper(page, base_url="https://mirror.betplay.test/").navigate(match)

    assert page.goto_calls == [
        "https://mirror.betplay.test/apuestas/futbol/junior-fc-vs-america-de-cali"
    ]


async def test_navigate_applies_the_configured_request_delay(
    match: Match, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(base_module, "asyncio", SimpleNamespace(sleep=record_sleep))

    page = FakePage()
    await make_scraper(page, request_delay_seconds=1.5).navigate(match)

    assert sleeps == [1.5]


async def test_navigate_retries_transient_failures_then_succeeds(match: Match) -> None:
    page = FakePage()
    page.goto_failures = [PlaywrightTimeoutError("net::ERR_TIMED_OUT")]

    await make_scraper(page).navigate(match)

    assert page.goto_calls == [MATCH_URL, MATCH_URL]


async def test_navigate_raises_selector_not_found_when_the_page_never_renders(
    match: Match,
) -> None:
    page = FakePage()
    page.wait_failures = {
        BetplayScraper.match_page_ready_selector: [PlaywrightTimeoutError("timeout")] * 3
    }

    with pytest.raises(SelectorNotFoundError):
        await make_scraper(page).navigate(match)
    assert len(page.goto_calls) == 3  # all attempts exhausted


async def test_navigate_raises_scraping_error_for_non_timeout_browser_failures(
    match: Match,
) -> None:
    page = FakePage()
    page.goto_failures = [PlaywrightError("net::ERR_CONNECTION_REFUSED")] * 3

    with pytest.raises(ScrapingError) as exc_info:
        await make_scraper(page).navigate(match)
    assert not isinstance(exc_info.value, SelectorNotFoundError)


async def test_extract_match_odds_reads_and_parses_the_markets_container(
    match: Match, load_fixture: Callable[[str], str]
) -> None:
    page = FakePage(
        html_by_selector={
            BetplayScraper.match_odds_container_selector: load_fixture("betplay_match_odds.html")
        }
    )

    quotes = await make_scraper(page).extract_match_odds(match)

    assert len(quotes) == 7
    assert BetplayScraper.match_odds_container_selector in page.wait_calls


async def test_extract_match_odds_raises_when_the_container_never_appears(match: Match) -> None:
    page = FakePage()
    page.wait_failures = {
        BetplayScraper.match_odds_container_selector: [PlaywrightTimeoutError("timeout")] * 3
    }

    with pytest.raises(SelectorNotFoundError):
        await make_scraper(page).extract_match_odds(match)


async def test_extract_match_odds_translates_browser_read_failures(match: Match) -> None:
    page = FakePage()
    page.inner_html_failures = [PlaywrightError("page crashed")] * 3

    with pytest.raises(ScrapingError) as exc_info:
        await make_scraper(page).extract_match_odds(match)
    assert not isinstance(exc_info.value, SelectorNotFoundError)


async def test_extract_player_props_opens_the_players_tab_and_parses(
    match: Match, load_fixture: Callable[[str], str]
) -> None:
    page = FakePage(
        html_by_selector={
            BetplayScraper.props_container_selector: load_fixture("betplay_player_props.html")
        }
    )

    props = await make_scraper(page).extract_player_props(match)

    assert page.click_calls == [BetplayScraper.props_tab_selector]
    assert len(props) == 4


async def test_extract_player_props_raises_when_the_tab_is_never_clickable(match: Match) -> None:
    page = FakePage()
    page.click_failures = [PlaywrightTimeoutError("timeout")] * 3

    with pytest.raises(SelectorNotFoundError):
        await make_scraper(page).extract_player_props(match)


async def test_extract_player_props_translates_browser_click_failures(match: Match) -> None:
    page = FakePage()
    page.click_failures = [PlaywrightError("detached frame")] * 3

    with pytest.raises(ScrapingError) as exc_info:
        await make_scraper(page).extract_player_props(match)
    assert not isinstance(exc_info.value, SelectorNotFoundError)
