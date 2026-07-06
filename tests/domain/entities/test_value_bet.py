from datetime import datetime

import pytest

from src.domain.entities.league import League
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.selection import Selection
from src.domain.entities.team import Team
from src.domain.entities.value_bet import ValueBet
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.edge_percentage import EdgePercentage
from src.domain.value_objects.probability import Probability
from src.domain.value_objects.stake import Stake


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
def selection() -> Selection:
    return Selection(market_type=MarketType.MATCH_WINNER_1X2, outcome="Home")


def test_valid_value_bet_construction(match: Match, selection: Selection) -> None:
    value_bet = ValueBet(
        match=match,
        selection=selection,
        local_odds=DecimalOdds(2.20),
        fair_probability=Probability(0.5),
        edge=EdgePercentage(10.0),
        suggested_stake=Stake(25.0),
        model_source=ModelSource.MARKET,
    )
    assert value_bet.match is match
    assert value_bet.selection is selection
    assert value_bet.edge.value == 10.0
    assert value_bet.model_source is ModelSource.MARKET
    assert value_bet.lineup_confirmed is None


def test_lineup_confirmed_defaults_to_none_and_is_settable(match: Match, selection: Selection) -> None:
    value_bet = ValueBet(
        match=match,
        selection=selection,
        local_odds=DecimalOdds(2.20),
        fair_probability=Probability(0.5),
        edge=EdgePercentage(10.0),
        suggested_stake=Stake(25.0),
        model_source=ModelSource.STATISTICAL,
        lineup_confirmed=False,
    )
    assert value_bet.lineup_confirmed is False


@pytest.mark.parametrize("edge_value", [0.0, -5.0])
def test_value_bet_requires_positive_edge(
    match: Match, selection: Selection, edge_value: float
) -> None:
    with pytest.raises(ValueError):
        ValueBet(
            match=match,
            selection=selection,
            local_odds=DecimalOdds(2.20),
            fair_probability=Probability(0.5),
            edge=EdgePercentage(edge_value),
            suggested_stake=Stake(25.0),
            model_source=ModelSource.MARKET,
        )
