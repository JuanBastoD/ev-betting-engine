from collections.abc import Callable
from datetime import datetime, timezone

import pytest

from src.domain.entities.bet_result import BetResult
from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.league import League
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.selection import Selection
from src.domain.entities.settled_bet import SettledBet
from src.domain.entities.team import Team
from src.domain.entities.value_bet import ValueBet
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.edge_percentage import EdgePercentage
from src.domain.value_objects.probability import Probability
from src.domain.value_objects.stake import Stake


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
def betplay() -> Bookmaker:
    return Bookmaker(name="Betplay", is_sharp=False, region="CO")


@pytest.fixture
def stake_bookmaker() -> Bookmaker:
    return Bookmaker(name="Stake", is_sharp=False, region="CO")


@pytest.fixture
def make_settled_bet(match: Match) -> Callable[..., SettledBet]:
    def _make(
        *,
        fair_probability: float,
        result: BetResult,
        market_type: MarketType = MarketType.MATCH_WINNER_1X2,
        outcome: str = "Home",
        model_source: ModelSource = ModelSource.MARKET,
        bookmaker: Bookmaker | None = None,
        local_odds: float = 2.0,
        closing_sharp_odds: float | None = None,
        settled_at: datetime | None = None,
    ) -> SettledBet:
        value_bet = ValueBet(
            match=match,
            selection=Selection(market_type=market_type, outcome=outcome),
            local_odds=DecimalOdds(local_odds),
            fair_probability=Probability(fair_probability),
            edge=EdgePercentage(1.0),
            suggested_stake=Stake(0.01),
            model_source=model_source,
            bookmaker=bookmaker,
        )
        return SettledBet(
            value_bet=value_bet,
            result=result,
            settled_at=settled_at or datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc),
            closing_sharp_odds=(
                DecimalOdds(closing_sharp_odds) if closing_sharp_odds is not None else None
            ),
        )

    return _make
