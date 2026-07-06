from datetime import datetime, timezone

import pytest

from src.application.exceptions import ValueBetNotFoundError
from src.application.use_cases.settle_bet import SettleBetUseCase
from src.domain.entities.bet_result import BetResult
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.selection import Selection
from src.domain.entities.value_bet import ValueBet
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.edge_percentage import EdgePercentage
from src.domain.value_objects.probability import Probability
from src.domain.value_objects.stake import Stake
from tests.fakes import FakeSettledBetRepository, FakeValueBetRepository


def _bet(match: Match, *, outcome: str = "Home", local_odds: float = 2.20) -> ValueBet:
    return ValueBet(
        match=match,
        selection=Selection(market_type=MarketType.MATCH_WINNER_1X2, outcome=outcome),
        local_odds=DecimalOdds(local_odds),
        fair_probability=Probability(0.5),
        edge=EdgePercentage(10.0),
        suggested_stake=Stake(0.02),
        model_source=ModelSource.MARKET,
    )


async def test_settles_a_matching_bet_by_natural_key(match: Match) -> None:
    value_bet_repository = FakeValueBetRepository()
    await value_bet_repository.save(_bet(match))
    settled_bet_repository = FakeSettledBetRepository()
    use_case = SettleBetUseCase(
        value_bet_repository=value_bet_repository, settled_bet_repository=settled_bet_repository
    )
    settled_at = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)

    settled_bet = await use_case.execute(
        match_id=match.id,
        market_type=MarketType.MATCH_WINNER_1X2,
        outcome="Home",
        line=None,
        local_odds=2.20,
        result=BetResult.WON,
        settled_at=settled_at,
    )

    assert settled_bet.result is BetResult.WON
    assert settled_bet.value_bet.match.id == match.id
    assert settled_bet_repository.saved == [settled_bet]


async def test_settles_with_a_closing_sharp_odds_for_clv(match: Match) -> None:
    value_bet_repository = FakeValueBetRepository()
    await value_bet_repository.save(_bet(match))
    use_case = SettleBetUseCase(
        value_bet_repository=value_bet_repository,
        settled_bet_repository=FakeSettledBetRepository(),
    )

    settled_bet = await use_case.execute(
        match_id=match.id,
        market_type=MarketType.MATCH_WINNER_1X2,
        outcome="Home",
        line=None,
        local_odds=2.20,
        result=BetResult.WON,
        settled_at=datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc),
        closing_sharp_odds=DecimalOdds(2.00),
    )

    assert settled_bet.clv is not None


async def test_raises_when_no_matching_value_bet_exists(match: Match) -> None:
    use_case = SettleBetUseCase(
        value_bet_repository=FakeValueBetRepository(),
        settled_bet_repository=FakeSettledBetRepository(),
    )

    with pytest.raises(ValueBetNotFoundError):
        await use_case.execute(
            match_id=match.id,
            market_type=MarketType.MATCH_WINNER_1X2,
            outcome="Home",
            line=None,
            local_odds=2.20,
            result=BetResult.WON,
            settled_at=datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc),
        )


async def test_natural_key_distinguishes_odds_at_the_same_outcome(match: Match) -> None:
    value_bet_repository = FakeValueBetRepository()
    await value_bet_repository.save(_bet(match, local_odds=2.20))
    use_case = SettleBetUseCase(
        value_bet_repository=value_bet_repository,
        settled_bet_repository=FakeSettledBetRepository(),
    )

    with pytest.raises(ValueBetNotFoundError):
        await use_case.execute(
            match_id=match.id,
            market_type=MarketType.MATCH_WINNER_1X2,
            outcome="Home",
            line=None,
            local_odds=1.80,  # no ValueBet was detected at this price
            result=BetResult.WON,
            settled_at=datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc),
        )
