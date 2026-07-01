"""Shared exceptions for external data-provider adapters (odds, stats, ...).

Any concrete provider adapter (The Odds API today, Sportmonks or others
later) must translate transport-level failures (httpx errors, bad status
codes, unparseable payloads) into one of these before they reach the
application/domain layers - neither layer should ever have to know httpx
exists.
"""


class ProviderError(Exception):
    """Base class for all provider-adapter errors."""


class ProviderUnavailableError(ProviderError):
    """The provider could not be reached, returned a server/client error
    (other than rate limiting), or sent a response that couldn't be parsed
    into the expected shape."""


class RateLimitError(ProviderError):
    """The provider rejected the request due to rate limiting (HTTP 429)."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after
