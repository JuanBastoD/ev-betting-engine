from collections.abc import Callable
from datetime import datetime, timezone

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
def home_team() -> Team:
    return Team(id="team-home", name="River Plate", country="Argentina")


@pytest.fixture
def away_team() -> Team:
    return Team(id="team-away", name="Boca Juniors", country="Argentina")


@pytest.fixture
def league() -> League:
    return League(id="league-1", name="Liga Profesional", country="Argentina")


@pytest.fixture
def match(home_team: Team, away_team: Team, league: League) -> Match:
    return Match(
        id="match-1",
        home_team=home_team,
        away_team=away_team,
        league=league,
        kickoff_utc=datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sharp_bookmaker() -> Bookmaker:
    return Bookmaker(name="Pinnacle", is_sharp=True, region="EU")


@pytest.fixture
def local_bookmaker() -> Bookmaker:
    return Bookmaker(name="Betplay", is_sharp=False, region="CO")


@pytest.fixture
def make_quote() -> Callable[..., OddsQuote]:
    def _make(
        match: Match,
        bookmaker: Bookmaker,
        market_type: MarketType,
        outcome: str,
        odds_value: float,
        *,
        line: float | None = None,
        quoted_at: datetime | None = None,
    ) -> OddsQuote:
        return OddsQuote(
            match=match,
            bookmaker=bookmaker,
            selection=Selection(market_type=market_type, outcome=outcome, line=line),
            odds=DecimalOdds(odds_value),
            quoted_at=quoted_at or datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc),
        )

    return _make
