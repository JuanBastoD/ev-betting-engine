"""Playwright-based scraping adapters for local (Colombian) bookmakers.

Importing this package wires every concrete scraper into `ScraperFactory`'s
registry - orchestrating code should import from here rather than from the
individual scraper modules.
"""

from src.infrastructure.providers.scraping.base import AbstractBookmakerScraper
from src.infrastructure.providers.scraping.betano import BetanoScraper
from src.infrastructure.providers.scraping.betplay import BetplayScraper
from src.infrastructure.providers.scraping.browser import PlaywrightBrowserSession
from src.infrastructure.providers.scraping.exceptions import (
    OddsParsingError,
    ScrapingError,
    SelectorNotFoundError,
)
from src.infrastructure.providers.scraping.factory import ScraperFactory
from src.infrastructure.providers.scraping.provider import PlaywrightLocalOddsProvider
from src.infrastructure.providers.scraping.stake import StakeScraper

__all__ = [
    "AbstractBookmakerScraper",
    "BetanoScraper",
    "BetplayScraper",
    "OddsParsingError",
    "PlaywrightBrowserSession",
    "PlaywrightLocalOddsProvider",
    "ScraperFactory",
    "ScrapingError",
    "SelectorNotFoundError",
    "StakeScraper",
]
