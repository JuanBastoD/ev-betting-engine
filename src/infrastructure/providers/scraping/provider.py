"""High-level adapter implementing the domain's LocalOddsProvider port by
scraping one local bookmaker's site with Playwright.

Scoped to a single bookmaker per instance (mirroring how
TheOddsApiSharpOddsProvider is scoped to one sport_key): the composition root
builds one provider per local bookmaker being scanned, all sharing one
PlaywrightBrowserSession. Each call gets a fresh Page that is always closed,
even when scraping fails mid-flight.
"""

from typing import Any

from playwright.async_api import Page

from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.ports.local_odds_provider import LocalOddsProvider
from src.infrastructure.providers.scraping.base import AbstractBookmakerScraper
from src.infrastructure.providers.scraping.browser import PlaywrightBrowserSession
from src.infrastructure.providers.scraping.factory import ScraperFactory


class PlaywrightLocalOddsProvider(LocalOddsProvider):
    """`LocalOddsProvider` backed by a registered bookmaker scraper.

    `scraper_kwargs` are forwarded verbatim to the scraper constructor
    (base_url, timeouts, request delay, retry tuning...), so operational
    limits stay configurable from the composition root.
    """

    def __init__(
        self,
        session: PlaywrightBrowserSession,
        bookmaker_name: str,
        **scraper_kwargs: Any,
    ) -> None:
        self._session = session
        self._bookmaker_name = bookmaker_name
        self._scraper_kwargs = scraper_kwargs

    async def get_odds(self, match: Match) -> list[OddsQuote]:
        page = await self._session.new_page()
        try:
            scraper = self._make_scraper(page)
            await scraper.navigate(match)
            return await scraper.extract_match_odds(match)
        finally:
            await page.close()

    async def get_player_props(self, match: Match) -> list[PlayerPropMarket]:
        page = await self._session.new_page()
        try:
            scraper = self._make_scraper(page)
            await scraper.navigate(match)
            return await scraper.extract_player_props(match)
        finally:
            await page.close()

    def _make_scraper(self, page: Page) -> AbstractBookmakerScraper:
        return ScraperFactory.create(self._bookmaker_name, page, **self._scraper_kwargs)
