"""Exceptions raised by the scraping adapters.

They extend the shared provider-error hierarchy so application code that
already handles `ProviderError` for the API adapters gets scraping failures
through the same funnel - no Playwright exception may leak past this package.
"""

from src.infrastructure.providers.exceptions import ProviderError


class ScrapingError(ProviderError):
    """A bookmaker page could not be scraped (navigation failure, unexpected
    page structure, browser-level error) after any configured retries."""


class SelectorNotFoundError(ScrapingError):
    """An expected element never appeared on the page (or is missing from a
    scraped HTML fragment) - usually a sign the site changed its markup."""


class OddsParsingError(ScrapingError):
    """Scraped text could not be converted into a valid domain value
    (e.g. an odds string that isn't a decimal number, or is <= 1.0)."""
