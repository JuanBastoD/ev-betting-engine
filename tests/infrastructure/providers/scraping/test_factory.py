import pytest

from src.infrastructure.providers.scraping.betano import BetanoScraper
from src.infrastructure.providers.scraping.betplay import BetplayScraper
from src.infrastructure.providers.scraping.factory import ScraperFactory
from src.infrastructure.providers.scraping.stake import StakeScraper
from tests.infrastructure.providers.scraping.fakes import FakePage


@pytest.mark.parametrize(
    ("name", "expected_cls"),
    [
        ("Betplay", BetplayScraper),
        ("Stake", StakeScraper),
        ("Betano", BetanoScraper),
        ("BETPLAY", BetplayScraper),  # case-insensitive lookup
        ("betano", BetanoScraper),
    ],
)
def test_create_returns_the_scraper_registered_for_the_bookmaker(
    name: str, expected_cls: type
) -> None:
    scraper = ScraperFactory.create(name, FakePage())
    assert type(scraper) is expected_cls


def test_create_forwards_scraper_kwargs() -> None:
    scraper = ScraperFactory.create("Betplay", FakePage(), region="LATAM", request_delay_seconds=0.0)
    assert scraper._bookmaker.region == "LATAM"


def test_create_rejects_unknown_bookmakers() -> None:
    with pytest.raises(ValueError, match="Wplay"):
        ScraperFactory.create("Wplay", FakePage())


def test_supported_bookmakers_lists_registered_names_sorted() -> None:
    assert ScraperFactory.supported_bookmakers() == ("Betano", "Betplay", "Stake")


def test_registering_a_new_scraper_requires_no_orchestrator_changes() -> None:
    class WplayScraper(BetplayScraper):
        bookmaker_name = "Wplay"

    try:
        ScraperFactory.register(WplayScraper)
        assert type(ScraperFactory.create("wplay", FakePage())) is WplayScraper
        assert "Wplay" in ScraperFactory.supported_bookmakers()
    finally:
        del ScraperFactory._registry["wplay"]

    assert ScraperFactory.supported_bookmakers() == ("Betano", "Betplay", "Stake")
