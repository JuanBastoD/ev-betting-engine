"""Registry-based factory: bookmaker name -> concrete scraper.

Adding a new bookmaker means writing one `AbstractBookmakerScraper` subclass
decorated with `@ScraperFactory.register` (and importing it from the package
`__init__`) - no orchestrating code changes.
"""

from typing import Any, ClassVar

from playwright.async_api import Page

from src.infrastructure.providers.scraping.base import AbstractBookmakerScraper


class ScraperFactory:
    _registry: ClassVar[dict[str, type[AbstractBookmakerScraper]]] = {}

    @classmethod
    def register(
        cls, scraper_cls: type[AbstractBookmakerScraper]
    ) -> type[AbstractBookmakerScraper]:
        """Class decorator: file the scraper under its (case-insensitive) name."""
        cls._registry[scraper_cls.bookmaker_name.casefold()] = scraper_cls
        return scraper_cls

    @classmethod
    def supported_bookmakers(cls) -> tuple[str, ...]:
        return tuple(sorted(scraper.bookmaker_name for scraper in cls._registry.values()))

    @classmethod
    def create(
        cls, bookmaker_name: str, page: Page, **scraper_kwargs: Any
    ) -> AbstractBookmakerScraper:
        try:
            scraper_cls = cls._registry[bookmaker_name.casefold()]
        except KeyError:
            raise ValueError(
                f"No scraper registered for bookmaker {bookmaker_name!r}; "
                f"supported: {', '.join(cls.supported_bookmakers())}"
            ) from None
        return scraper_cls(page, **scraper_kwargs)
