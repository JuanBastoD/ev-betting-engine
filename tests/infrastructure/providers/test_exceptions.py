from src.infrastructure.providers.exceptions import (
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
)


def test_provider_unavailable_error_is_a_provider_error() -> None:
    error = ProviderUnavailableError("boom")

    assert isinstance(error, ProviderError)
    assert str(error) == "boom"


def test_rate_limit_error_carries_optional_retry_after() -> None:
    error = RateLimitError("rate limited", retry_after=1.5)

    assert isinstance(error, ProviderError)
    assert str(error) == "rate limited"
    assert error.retry_after == 1.5


def test_rate_limit_error_retry_after_defaults_to_none() -> None:
    error = RateLimitError("rate limited")

    assert error.retry_after is None
