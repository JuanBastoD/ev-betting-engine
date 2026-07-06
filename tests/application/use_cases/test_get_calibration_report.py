from datetime import datetime, timezone

from src.application.use_cases.get_calibration_report import GetCalibrationReportUseCase
from src.domain.entities.bet_result import BetResult
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.selection import Selection
from src.domain.entities.settled_bet import SettledBet
from src.domain.entities.value_bet import ValueBet
from src.domain.services.calibration.calibration_service import CalibrationService
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.edge_percentage import EdgePercentage
from src.domain.value_objects.probability import Probability
from src.domain.value_objects.stake import Stake
from tests.fakes import FakeSettledBetRepository


def _settled_bet(
    match: Match,
    *,
    market_type: MarketType = MarketType.MATCH_WINNER_1X2,
    model_source: ModelSource = ModelSource.MARKET,
    fair_probability: float = 0.5,
    result: BetResult = BetResult.WON,
) -> SettledBet:
    value_bet = ValueBet(
        match=match,
        selection=Selection(market_type=market_type, outcome="Home"),
        local_odds=DecimalOdds(2.0),
        fair_probability=Probability(fair_probability),
        edge=EdgePercentage(5.0),
        suggested_stake=Stake(0.01),
        model_source=model_source,
    )
    return SettledBet(
        value_bet=value_bet, result=result, settled_at=datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
    )


async def test_returns_a_segmented_report_over_every_settled_bet(match: Match) -> None:
    repository = FakeSettledBetRepository()
    await repository.save(_settled_bet(match))
    await repository.save(_settled_bet(match, result=BetResult.LOST))
    use_case = GetCalibrationReportUseCase(
        settled_bet_repository=repository, calibration_service=CalibrationService()
    )

    report = await use_case.execute()

    assert report.overall.sample_size == 2


async def test_filters_by_model_source_before_segmenting(match: Match) -> None:
    repository = FakeSettledBetRepository()
    await repository.save(_settled_bet(match, model_source=ModelSource.MARKET))
    await repository.save(_settled_bet(match, model_source=ModelSource.STATISTICAL))
    use_case = GetCalibrationReportUseCase(
        settled_bet_repository=repository, calibration_service=CalibrationService()
    )

    report = await use_case.execute(model_source=ModelSource.STATISTICAL)

    assert report.overall.sample_size == 1


async def test_filters_by_market_type_before_segmenting(match: Match) -> None:
    repository = FakeSettledBetRepository()
    await repository.save(_settled_bet(match, market_type=MarketType.MATCH_WINNER_1X2))
    await repository.save(_settled_bet(match, market_type=MarketType.OVER_UNDER))
    use_case = GetCalibrationReportUseCase(
        settled_bet_repository=repository, calibration_service=CalibrationService()
    )

    report = await use_case.execute(market_type=MarketType.OVER_UNDER)

    assert report.overall.sample_size == 1


async def test_filters_combine_with_and_semantics(match: Match) -> None:
    repository = FakeSettledBetRepository()
    await repository.save(
        _settled_bet(match, market_type=MarketType.MATCH_WINNER_1X2, model_source=ModelSource.MARKET)
    )
    await repository.save(
        _settled_bet(match, market_type=MarketType.OVER_UNDER, model_source=ModelSource.MARKET)
    )
    use_case = GetCalibrationReportUseCase(
        settled_bet_repository=repository, calibration_service=CalibrationService()
    )

    report = await use_case.execute(
        market_type=MarketType.MATCH_WINNER_1X2, model_source=ModelSource.MARKET
    )

    assert report.overall.sample_size == 1
