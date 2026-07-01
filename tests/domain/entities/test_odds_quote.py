from datetime import datetime, timedelta, timezone

import pytest

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.market_type import MarketType
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.selection import Selection
from src.domain.value_objects.decimal_odds import DecimalOdds


@pytest.fixture
def bookmaker() -> Bookmaker:
    return Bookmaker(name="Pinnacle", is_sharp=True, region="EU")


@pytest.fixture
def selection() -> Selection:
    return Selection(market_type=MarketType.MATCH_WINNER_1X2, outcome="Home")


def test_valid_odds_quote_construction(bookmaker: Bookmaker, selection: Selection) -> None:
    quoted_at = datetime(2026, 8, 15, 19, 0, tzinfo=timezone.utc)
    quote = OddsQuote(
        bookmaker=bookmaker, selection=selection, odds=DecimalOdds(1.95), quoted_at=quoted_at
    )
    assert quote.bookmaker is bookmaker
    assert quote.selection is selection
    assert quote.odds.value == 1.95
    assert quote.quoted_at == quoted_at


def test_odds_quote_requires_timezone_aware_timestamp(
    bookmaker: Bookmaker, selection: Selection
) -> None:
    with pytest.raises(ValueError):
        OddsQuote(
            bookmaker=bookmaker,
            selection=selection,
            odds=DecimalOdds(1.95),
            quoted_at=datetime(2026, 8, 15, 19, 0),
        )


def test_odds_quote_requires_utc_timestamp(bookmaker: Bookmaker, selection: Selection) -> None:
    with pytest.raises(ValueError):
        OddsQuote(
            bookmaker=bookmaker,
            selection=selection,
            odds=DecimalOdds(1.95),
            quoted_at=datetime(2026, 8, 15, 19, 0, tzinfo=timezone(timedelta(hours=2))),
        )
