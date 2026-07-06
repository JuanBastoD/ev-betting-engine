"""Hand-derived checks for `SettledBet.profit_loss`/`SettledBet.clv`.

profit_loss (stake=0.025, odds=2.20):
    WON  -> 0.025 * (2.20 - 1) = 0.025 * 1.20 = 0.03
    LOST -> -0.025
    PUSH -> 0.0

clv (local_odds=2.20, closing_sharp_odds=2.00):
    implied(2.20) = 1/2.20 = 0.4545454545...
    implied(2.00) = 1/2.00 = 0.5
    clv = 0.5 - 0.4545454545... = 0.0454545454...
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.domain.entities.bet_result import BetResult
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
def match(home_team: Team, away_team: Team, league: League, kickoff_utc: datetime) -> Match:
    return Match(
        id="match-1", home_team=home_team, away_team=away_team, league=league, kickoff_utc=kickoff_utc
    )


@pytest.fixture
def value_bet(match: Match) -> ValueBet:
    return ValueBet(
        match=match,
        selection=Selection(market_type=MarketType.MATCH_WINNER_1X2, outcome="Home"),
        local_odds=DecimalOdds(2.20),
        fair_probability=Probability(0.5),
        edge=EdgePercentage(10.0),
        suggested_stake=Stake(0.025),
        model_source=ModelSource.MARKET,
    )


@pytest.fixture
def settled_at() -> datetime:
    return datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def test_valid_settled_bet_construction(value_bet: ValueBet, settled_at: datetime) -> None:
    settled_bet = SettledBet(value_bet=value_bet, result=BetResult.WON, settled_at=settled_at)
    assert settled_bet.value_bet is value_bet
    assert settled_bet.result is BetResult.WON
    assert settled_bet.closing_sharp_odds is None


def test_won_profit_loss(value_bet: ValueBet, settled_at: datetime) -> None:
    settled_bet = SettledBet(value_bet=value_bet, result=BetResult.WON, settled_at=settled_at)
    assert settled_bet.profit_loss == pytest.approx(0.03)


def test_lost_profit_loss(value_bet: ValueBet, settled_at: datetime) -> None:
    settled_bet = SettledBet(value_bet=value_bet, result=BetResult.LOST, settled_at=settled_at)
    assert settled_bet.profit_loss == pytest.approx(-0.025)


def test_push_profit_loss(value_bet: ValueBet, settled_at: datetime) -> None:
    settled_bet = SettledBet(value_bet=value_bet, result=BetResult.PUSH, settled_at=settled_at)
    assert settled_bet.profit_loss == 0.0


def test_clv_is_none_without_closing_sharp_odds(value_bet: ValueBet, settled_at: datetime) -> None:
    settled_bet = SettledBet(value_bet=value_bet, result=BetResult.WON, settled_at=settled_at)
    assert settled_bet.clv is None


def test_clv_hand_derived(value_bet: ValueBet, settled_at: datetime) -> None:
    settled_bet = SettledBet(
        value_bet=value_bet,
        result=BetResult.WON,
        settled_at=settled_at,
        closing_sharp_odds=DecimalOdds(2.00),
    )
    assert settled_bet.clv == pytest.approx(0.045454545454545464)


def test_settled_at_requires_timezone_aware_datetime(value_bet: ValueBet) -> None:
    with pytest.raises(ValueError):
        SettledBet(value_bet=value_bet, result=BetResult.WON, settled_at=datetime(2026, 8, 16, 12, 0))


def test_settled_at_requires_utc(value_bet: ValueBet) -> None:
    non_utc = timezone(timedelta(hours=-3))
    with pytest.raises(ValueError):
        SettledBet(
            value_bet=value_bet,
            result=BetResult.WON,
            settled_at=datetime(2026, 8, 16, 12, 0, tzinfo=non_utc),
        )
