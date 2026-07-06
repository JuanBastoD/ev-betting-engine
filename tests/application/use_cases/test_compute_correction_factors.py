from datetime import datetime, timezone

from src.application.use_cases.compute_correction_factors import (
    ComputeCorrectionFactorsUseCase,
)
from src.domain.entities.bet_result import BetResult
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.selection import Selection
from src.domain.entities.settled_bet import SettledBet
from src.domain.entities.value_bet import ValueBet
from src.domain.services.calibration.correction_factor import CorrectionFactorService
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.edge_percentage import EdgePercentage
from src.domain.value_objects.probability import Probability
from src.domain.value_objects.stake import Stake
from tests.fakes import FakeCorrectionFactorRepository, FakeSettledBetRepository


def _settled_bet(match: Match, *, result: BetResult) -> SettledBet:
    value_bet = ValueBet(
        match=match,
        selection=Selection(market_type=MarketType.MATCH_WINNER_1X2, outcome="Home"),
        local_odds=DecimalOdds(2.0),
        fair_probability=Probability(0.5),
        edge=EdgePercentage(5.0),
        suggested_stake=Stake(0.01),
        model_source=ModelSource.MARKET,
    )
    return SettledBet(
        value_bet=value_bet, result=result, settled_at=datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
    )


async def test_computes_and_persists_correction_factors(match: Match) -> None:
    settled_bet_repository = FakeSettledBetRepository()
    await settled_bet_repository.save(_settled_bet(match, result=BetResult.WON))
    await settled_bet_repository.save(_settled_bet(match, result=BetResult.LOST))
    correction_factor_repository = FakeCorrectionFactorRepository()
    use_case = ComputeCorrectionFactorsUseCase(
        settled_bet_repository=settled_bet_repository,
        correction_factor_repository=correction_factor_repository,
        correction_factor_service=CorrectionFactorService(min_sample_size=2),
    )
    computed_at = datetime(2026, 9, 1, tzinfo=timezone.utc)

    factors = await use_case.execute(computed_at=computed_at)

    assert len(factors) > 0
    assert correction_factor_repository.saved == factors


async def test_under_sampled_segments_produce_no_persisted_factors(match: Match) -> None:
    settled_bet_repository = FakeSettledBetRepository()
    await settled_bet_repository.save(_settled_bet(match, result=BetResult.WON))
    correction_factor_repository = FakeCorrectionFactorRepository()
    use_case = ComputeCorrectionFactorsUseCase(
        settled_bet_repository=settled_bet_repository,
        correction_factor_repository=correction_factor_repository,
        correction_factor_service=CorrectionFactorService(min_sample_size=100),
    )

    factors = await use_case.execute(computed_at=datetime(2026, 9, 1, tzinfo=timezone.utc))

    assert factors == []
    assert correction_factor_repository.saved == []
