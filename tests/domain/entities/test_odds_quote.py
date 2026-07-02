from datetime import datetime, timedelta, timezone

import pytest

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.league import League
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.selection import Selection
from src.domain.entities.team import Team
from src.domain.value_objects.decimal_odds import DecimalOdds


@pytest.fixture
def match(home_team: Team, away_team: Team, league: League, kickoff_utc: datetime) -> Match:
    return Match(
        id="match-1",
        home_team=home_team,
        away_team=away_team,
        league=league,
        kickoff_utc=kickoff_utc,
    )


@pytest.fixture
def bookmaker() -> Bookmaker:
    return Bookmaker(name="Pinnacle", is_sharp=True, region="EU")


@pytest.fixture
def selection() -> Selection:
    return Selection(market_type=MarketType.MATCH_WINNER_1X2, outcome="Home")


def test_valid_odds_quote_construction(
    match: Match, bookmaker: Bookmaker, selection: Selection
) -> None:
    quoted_at = datetime(2026, 8, 15, 19, 0, tzinfo=timezone.utc)
    quote = OddsQuote(
        match=match,
        bookmaker=bookmaker,
        selection=selection,
        odds=DecimalOdds(1.95),
        quoted_at=quoted_at,
    )
    assert quote.match is match
    assert quote.bookmaker is bookmaker
    assert quote.selection is selection
    assert quote.odds.value == 1.95
    assert quote.quoted_at == quoted_at


def test_odds_quote_requires_timezone_aware_timestamp(
    match: Match, bookmaker: Bookmaker, selection: Selection
) -> None:
    with pytest.raises(ValueError):
        OddsQuote(
            match=match,
            bookmaker=bookmaker,
            selection=selection,
            odds=DecimalOdds(1.95),
            quoted_at=datetime(2026, 8, 15, 19, 0),
        )


def test_odds_quote_requires_utc_timestamp(
    match: Match, bookmaker: Bookmaker, selection: Selection
) -> None:
    with pytest.raises(ValueError):
        OddsQuote(
            match=match,
            bookmaker=bookmaker,
            selection=selection,
            odds=DecimalOdds(1.95),
            quoted_at=datetime(2026, 8, 15, 19, 0, tzinfo=timezone(timedelta(hours=2))),
        )
