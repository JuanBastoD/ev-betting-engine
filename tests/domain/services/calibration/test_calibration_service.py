"""Hand-derived checks for `CalibrationService`.

Brier/log-loss (predictions=[0.6, 0.7, 0.3], outcomes=[1, 1, 0], i.e.
WON/WON/LOST):

    brier = mean((p-o)^2)
          = [(0.6-1)^2 + (0.7-1)^2 + (0.3-0)^2] / 3
          = [0.16 + 0.09 + 0.09] / 3 = 0.34 / 3 = 0.11333333333333336

    log_loss = -mean(o*ln(p) + (1-o)*ln(1-p))
             = -[ln(0.6) + ln(0.7) + ln(0.7)] / 3
             = -[-0.5108256238 - 0.3566749439 - 0.3566749439] / 3
             = 1.2241755116 / 3 = 0.4080585038811519

CLV (local_odds=2.20, closing_sharp_odds=2.00):
    implied(2.20) = 1/2.20 = 0.45454545...
    implied(2.00) = 1/2.00 = 0.5
    clv = 0.5 - 0.45454545... = 0.04545454545454547
"""

from collections.abc import Callable

import pytest

from src.domain.entities.bet_result import BetResult
from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.market_type import MarketType
from src.domain.entities.model_source import ModelSource
from src.domain.entities.settled_bet import SettledBet
from src.domain.services.calibration.calibration_service import CalibrationService, extract_prop_type


@pytest.fixture
def service() -> CalibrationService:
    return CalibrationService()


def test_brier_score_and_log_loss_hand_derived(
    service: CalibrationService, make_settled_bet: Callable[..., SettledBet]
) -> None:
    settled_bets = [
        make_settled_bet(fair_probability=0.6, result=BetResult.WON),
        make_settled_bet(fair_probability=0.7, result=BetResult.WON),
        make_settled_bet(fair_probability=0.3, result=BetResult.LOST),
    ]
    metrics = service.calculate(settled_bets)
    assert metrics.sample_size == 3
    assert metrics.brier_score == pytest.approx(0.11333333333333336)
    assert metrics.log_loss == pytest.approx(0.4080585038811519)


def test_average_clv_hand_derived_and_excludes_bets_without_closing_line(
    service: CalibrationService, make_settled_bet: Callable[..., SettledBet]
) -> None:
    settled_bets = [
        make_settled_bet(
            fair_probability=0.5,
            result=BetResult.WON,
            local_odds=2.20,
            closing_sharp_odds=2.00,
        ),
        make_settled_bet(fair_probability=0.5, result=BetResult.LOST),  # no closing line
    ]
    metrics = service.calculate(settled_bets)
    assert metrics.average_clv == pytest.approx(0.04545454545454547)


def test_push_results_excluded_from_brier_log_loss_but_not_clv(
    service: CalibrationService, make_settled_bet: Callable[..., SettledBet]
) -> None:
    settled_bets = [
        make_settled_bet(fair_probability=0.6, result=BetResult.WON),
        make_settled_bet(
            fair_probability=0.5,
            result=BetResult.PUSH,
            local_odds=2.0,
            closing_sharp_odds=2.10,
        ),
    ]
    metrics = service.calculate(settled_bets)
    assert metrics.sample_size == 1
    assert metrics.brier_score == pytest.approx((0.6 - 1.0) ** 2)
    assert metrics.average_clv is not None  # PUSH's CLV still counted


def test_empty_settled_bets_yields_none_metrics_and_empty_buckets(
    service: CalibrationService,
) -> None:
    metrics = service.calculate([])
    assert metrics.sample_size == 0
    assert metrics.brier_score is None
    assert metrics.log_loss is None
    assert metrics.average_clv is None
    assert len(metrics.calibration_curve) == 10
    for bucket in metrics.calibration_curve:
        assert bucket.predicted_mean is None
        assert bucket.observed_frequency is None
        assert bucket.sample_size == 0


def test_calibration_curve_synthetic_known_distribution(
    service: CalibrationService, make_settled_bet: Callable[..., SettledBet]
) -> None:
    settled_bets = [
        make_settled_bet(fair_probability=0.05, result=BetResult.WON),
        make_settled_bet(fair_probability=0.05, result=BetResult.LOST),
        make_settled_bet(fair_probability=0.15, result=BetResult.WON),
        make_settled_bet(fair_probability=0.95, result=BetResult.LOST),
    ]
    metrics = service.calculate(settled_bets)
    buckets = metrics.calibration_curve
    assert len(buckets) == 10

    bucket_0 = buckets[0]  # [0.0, 0.1)
    assert bucket_0.sample_size == 2
    assert bucket_0.predicted_mean == pytest.approx(0.05)
    assert bucket_0.observed_frequency == pytest.approx(0.5)

    bucket_1 = buckets[1]  # [0.1, 0.2)
    assert bucket_1.sample_size == 1
    assert bucket_1.predicted_mean == pytest.approx(0.15)
    assert bucket_1.observed_frequency == pytest.approx(1.0)

    bucket_9 = buckets[9]  # [0.9, 1.0]
    assert bucket_9.sample_size == 1
    assert bucket_9.predicted_mean == pytest.approx(0.95)
    assert bucket_9.observed_frequency == pytest.approx(0.0)

    for index in (2, 3, 4, 5, 6, 7, 8):
        assert buckets[index].sample_size == 0
        assert buckets[index].predicted_mean is None
        assert buckets[index].observed_frequency is None


def test_bucket_width_validation() -> None:
    with pytest.raises(ValueError):
        CalibrationService(bucket_width=0.0)
    with pytest.raises(ValueError):
        CalibrationService(bucket_width=1.5)


def test_calculate_segmented_groups_by_market_type_bookmaker_model_source_and_prop_type(
    service: CalibrationService,
    make_settled_bet: Callable[..., SettledBet],
    betplay: Bookmaker,
    stake_bookmaker: Bookmaker,
) -> None:
    settled_bets = [
        make_settled_bet(
            fair_probability=0.6,
            result=BetResult.WON,
            market_type=MarketType.MATCH_WINNER_1X2,
            model_source=ModelSource.MARKET,
            bookmaker=betplay,
        ),
        make_settled_bet(
            fair_probability=0.4,
            result=BetResult.LOST,
            market_type=MarketType.OVER_UNDER,
            model_source=ModelSource.STATISTICAL,
            bookmaker=stake_bookmaker,
        ),
        make_settled_bet(
            fair_probability=0.7,
            result=BetResult.WON,
            market_type=MarketType.PLAYER_PROP,
            outcome="Lionel Messi SHOTS_ON_TARGET Over",
            model_source=ModelSource.STATISTICAL,
            bookmaker=betplay,
        ),
    ]
    report = service.calculate_segmented(settled_bets)

    assert report.overall.sample_size == 3
    assert set(report.by_market_type.keys()) == {"MATCH_WINNER_1X2", "OVER_UNDER", "PLAYER_PROP"}
    assert report.by_market_type["MATCH_WINNER_1X2"].sample_size == 1
    assert set(report.by_bookmaker.keys()) == {"Betplay", "Stake"}
    assert report.by_bookmaker["Betplay"].sample_size == 2
    assert set(report.by_model_source.keys()) == {"MARKET", "STATISTICAL"}
    assert report.by_model_source["STATISTICAL"].sample_size == 2
    assert set(report.by_prop_type.keys()) == {"SHOTS_ON_TARGET"}
    assert report.by_prop_type["SHOTS_ON_TARGET"].sample_size == 1


def test_calculate_segmented_skips_bets_with_no_bookmaker(
    service: CalibrationService, make_settled_bet: Callable[..., SettledBet]
) -> None:
    settled_bets = [make_settled_bet(fair_probability=0.5, result=BetResult.WON, bookmaker=None)]
    report = service.calculate_segmented(settled_bets)
    assert report.by_bookmaker == {}


def test_calculate_segmented_skips_player_prop_bets_with_unrecognized_prop_type(
    service: CalibrationService, make_settled_bet: Callable[..., SettledBet]
) -> None:
    settled_bets = [
        make_settled_bet(
            fair_probability=0.5,
            result=BetResult.WON,
            market_type=MarketType.PLAYER_PROP,
            outcome="Lionel Messi UNKNOWN_METRIC Over",
        )
    ]
    report = service.calculate_segmented(settled_bets)
    assert report.by_prop_type == {}


def test_extract_prop_type_returns_matching_token() -> None:
    assert extract_prop_type("Lionel Messi SHOTS_ON_TARGET Over") is not None
    assert extract_prop_type("Lionel Messi SHOTS_ON_TARGET Over").value == "SHOTS_ON_TARGET"


def test_extract_prop_type_returns_none_when_no_known_prop_type_present() -> None:
    assert extract_prop_type("Lionel Messi UNKNOWN_METRIC Over") is None
