"""Abstract Page Object base for every local-bookmaker scraper.

Template Method: the shared flow (rate-limit delay -> navigate with retries
-> wait for selectors -> grab `inner_html` -> parse) lives here; each
concrete scraper owns only its URLs, its CSS selectors and the pure
HTML-fragment parsing for its markup. Playwright touches exactly three
operations (`goto`, `wait_for_selector`, `inner_html`/`click`), which keeps
the Page surface small enough to fake in tests.

Retries mirror the API clients (Prompt 3/4): a tenacity `AsyncRetrying`
scoped to transient Playwright errors, with wait/attempt parameters as
constructor args so tests pass near-zero backoff. Exhausted retries are
translated into the scraping exception hierarchy - no Playwright exception
may leak past this package.
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import ClassVar

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.entities.player_prop_type import PlayerPropType
from src.domain.entities.selection import Selection
from src.infrastructure.providers.scraping.exceptions import ScrapingError, SelectorNotFoundError
from src.infrastructure.providers.scraping.html_utils import Element
from src.infrastructure.providers.scraping.parsing import parse_decimal_odds, parse_line_value


class AbstractBookmakerScraper(ABC):
    """Base Page Object for one bookmaker's match page.

    Subclasses must define the class-level selectors below, plus `match_url`
    and the two pure parsing hooks. 1X2 parsing is position-based by
    convention (first selection = Home, second = Draw, third = Away), because
    sites routinely abbreviate team names in ways that defeat name matching.
    """

    bookmaker_name: ClassVar[str]
    default_base_url: ClassVar[str]
    # Selector that signals the match page finished rendering its odds UI.
    match_page_ready_selector: ClassVar[str]
    # Container whose inner HTML holds the main match markets (1X2/totals/BTTS).
    match_odds_container_selector: ClassVar[str]
    # Tab/section toggle that reveals the player-props ("Jugadores"/"Especiales") panel.
    props_tab_selector: ClassVar[str]
    # Container whose inner HTML holds the player-prop cards.
    props_container_selector: ClassVar[str]

    def __init__(
        self,
        page: Page,
        *,
        base_url: str | None = None,
        region: str = "CO",
        nav_timeout_ms: float = 30_000,
        selector_timeout_ms: float = 10_000,
        request_delay_seconds: float = 1.0,
        max_attempts: int = 3,
        wait_min: float = 0.5,
        wait_max: float = 4.0,
        wait_multiplier: float = 0.5,
    ) -> None:
        self._page = page
        self._base_url = (base_url or self.default_base_url).rstrip("/")
        self._bookmaker = Bookmaker(name=self.bookmaker_name, is_sharp=False, region=region)
        self._nav_timeout_ms = nav_timeout_ms
        self._selector_timeout_ms = selector_timeout_ms
        self._request_delay_seconds = request_delay_seconds
        self._retrying = AsyncRetrying(
            retry=retry_if_exception_type(PlaywrightError),
            wait=wait_exponential(multiplier=wait_multiplier, min=wait_min, max=wait_max),
            stop=stop_after_attempt(max_attempts),
            reraise=True,
        )

    # --- site-specific hooks -------------------------------------------------

    @abstractmethod
    def match_url(self, match: Match) -> str:
        """Absolute URL of this bookmaker's page for `match`."""

    @abstractmethod
    def parse_match_odds(self, html: str, match: Match) -> list[OddsQuote]:
        """Pure: main-markets container HTML -> OddsQuotes (1X2/totals/BTTS)."""

    @abstractmethod
    def parse_player_props(self, html: str, match: Match) -> list[PlayerPropMarket]:
        """Pure: player-props container HTML -> PlayerPropMarkets."""

    # --- template methods (the shared scraping flow) --------------------------

    async def navigate(self, match: Match) -> None:
        """Open the bookmaker's match page and wait until its odds UI rendered."""
        if self._request_delay_seconds > 0:
            await asyncio.sleep(self._request_delay_seconds)
        url = self.match_url(match)
        try:
            await self._retrying(self._goto_and_wait, url)
        except PlaywrightTimeoutError as exc:
            raise SelectorNotFoundError(
                f"{self.bookmaker_name}: match page at {url} never became ready "
                f"(selector {self.match_page_ready_selector!r})"
            ) from exc
        except PlaywrightError as exc:
            raise ScrapingError(f"{self.bookmaker_name}: navigation to {url} failed: {exc}") from exc

    async def extract_match_odds(self, match: Match) -> list[OddsQuote]:
        """Read the main match markets from the already-navigated page."""
        html = await self._inner_html(self.match_odds_container_selector)
        return self.parse_match_odds(html, match)

    async def extract_player_props(self, match: Match) -> list[PlayerPropMarket]:
        """Open the players/specials section and read the prop markets."""
        await self._click(self.props_tab_selector)
        html = await self._inner_html(self.props_container_selector)
        return self.parse_player_props(html, match)

    # --- assembly/parsing helpers for subclasses ------------------------------

    def _quote(
        self,
        *,
        market_type: MarketType,
        outcome: str,
        odds_text: str,
        quoted_at: datetime,
        line: float | None = None,
    ) -> OddsQuote:
        return OddsQuote(
            bookmaker=self._bookmaker,
            selection=Selection(market_type=market_type, outcome=outcome, line=line),
            odds=parse_decimal_odds(odds_text),
            quoted_at=quoted_at,
        )

    def _prop(
        self,
        *,
        match: Match,
        player_name: str,
        prop_type: PlayerPropType,
        outcome: str,
        line: float | None,
        odds_text: str,
        quoted_at: datetime,
    ) -> PlayerPropMarket:
        return PlayerPropMarket(
            match=match,
            bookmaker=self._bookmaker,
            player_name=player_name,
            prop_type=prop_type,
            outcome=outcome,
            line=line,
            odds=parse_decimal_odds(odds_text),
            quoted_at=quoted_at,
        )

    @staticmethod
    def _required_text(element: Element, class_name: str) -> str:
        child = element.find(class_name)
        if child is None:
            raise SelectorNotFoundError(
                f"Expected an element with class {class_name!r} inside the scraped fragment"
            )
        return child.text

    @staticmethod
    def _parse_over_under_label(
        label: str, *, over_prefix: str, under_prefix: str
    ) -> tuple[str, float] | None:
        """'Más de 2,5' -> ('Over', 2.5); unrecognized labels -> None so the
        caller can skip rows for markets we don't model."""
        folded = label.casefold().strip()
        if folded.startswith(over_prefix):
            return "Over", parse_line_value(label)
        if folded.startswith(under_prefix):
            return "Under", parse_line_value(label)
        return None

    # --- playwright plumbing ---------------------------------------------------

    async def _goto_and_wait(self, url: str) -> None:
        await self._page.goto(url, timeout=self._nav_timeout_ms, wait_until="domcontentloaded")
        await self._page.wait_for_selector(
            self.match_page_ready_selector, timeout=self._selector_timeout_ms
        )

    async def _inner_html(self, selector: str) -> str:
        try:
            return await self._retrying(self._wait_and_read, selector)
        except PlaywrightTimeoutError as exc:
            raise SelectorNotFoundError(
                f"{self.bookmaker_name}: selector {selector!r} never appeared"
            ) from exc
        except PlaywrightError as exc:
            raise ScrapingError(
                f"{self.bookmaker_name}: failed reading selector {selector!r}: {exc}"
            ) from exc

    async def _wait_and_read(self, selector: str) -> str:
        await self._page.wait_for_selector(selector, timeout=self._selector_timeout_ms)
        return await self._page.inner_html(selector)

    async def _click(self, selector: str) -> None:
        try:
            await self._retrying(self._raw_click, selector)
        except PlaywrightTimeoutError as exc:
            raise SelectorNotFoundError(
                f"{self.bookmaker_name}: clickable selector {selector!r} never appeared"
            ) from exc
        except PlaywrightError as exc:
            raise ScrapingError(
                f"{self.bookmaker_name}: failed clicking selector {selector!r}: {exc}"
            ) from exc

    async def _raw_click(self, selector: str) -> None:
        await self._page.click(selector, timeout=self._selector_timeout_ms)
