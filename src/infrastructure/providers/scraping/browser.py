"""Owns the Playwright browser lifecycle for the scraping adapters.

One session = one headless Chromium + one browser context (realistic
user-agent and viewport, so pages render their full desktop markets UI).
Scrapers get short-lived `Page`s out of it. Always used as an async context
manager - `close()` tears the stack down even when startup half-succeeded.
"""

from types import TracebackType
from typing import Self

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright.async_api import Error as PlaywrightError

from src.infrastructure.providers.scraping.exceptions import ScrapingError

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


class PlaywrightBrowserSession:
    def __init__(
        self,
        *,
        headless: bool = True,
        user_agent: str = DEFAULT_USER_AGENT,
        viewport_width: int = 1366,
        viewport_height: int = 768,
    ) -> None:
        self._headless = headless
        self._user_agent = user_agent
        self._viewport_width = viewport_width
        self._viewport_height = viewport_height
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch(headless=self._headless)
            self._context = await self._browser.new_context(
                user_agent=self._user_agent,
                viewport={"width": self._viewport_width, "height": self._viewport_height},
            )
        except Exception as exc:
            await self.close()
            if isinstance(exc, PlaywrightError):
                raise ScrapingError(f"Failed to start the headless browser: {exc}") from exc
            raise

    async def new_page(self) -> Page:
        if self._context is None:
            raise ScrapingError(
                "Browser session is not started - use 'async with' or call start() first"
            )
        return await self._context.new_page()

    async def close(self) -> None:
        """Release page context, browser and the Playwright driver, in that
        order, each step running even if the previous one failed."""
        context, self._context = self._context, None
        browser, self._browser = self._browser, None
        playwright, self._playwright = self._playwright, None
        try:
            if context is not None:
                await context.close()
        finally:
            try:
                if browser is not None:
                    await browser.close()
            finally:
                if playwright is not None:
                    await playwright.stop()
