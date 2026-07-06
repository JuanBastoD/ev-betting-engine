"""Hand-derived checks for `CorrectionFactorService`/`CorrectionFactor`.

Overall-segment factor (min_sample_size=2, fair_probability=0.5 for every
bet, results WON/WON/LOST):

    predicted_mean = 0.5
    observed_frequency = 2/3 = 0.6666666666666666
    factor = observed_frequency / predicted_mean = 1.3333333333333333

apply_correction_factor(0.5, factor=1.2) = 0.5 * 1.2 = 0.6
apply_correction_factor(0.9, factor=1.5) = 1.35, clamped to 1.0
"""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pytest

from src.domain.entities.bet_result import BetResult
from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.market_type import MarketType
from src.domain.entities.settled_bet import SettledBet
from src.domain.services.calibration.correction_factor import (
    CorrectionFactor,
    CorrectionFactorService,
    apply_correction_factor,
    latest_by_segment,
)
from src.domain.value_objects.probability import Probability

_COMPUTED_AT = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)


def test_overall_factor_hand_derived(make_settled_bet: Callable[..., SettledBet]) -> None:
    settled_bets = [
        make_settled_bet(fair_probability=0.5, result=BetResult.WON),
        make_settled_bet(fair_probability=0.5, result=BetResult.WON),
        make_settled_bet(fair_probability=0.5, result=BetResult.LOST),
    ]
    service = CorrectionFactorService(min_sample_size=2)
    factors = service.compute_factors(settled_bets, computed_at=_COMPUTED_AT)

    overall = next(f for f in factors if f.segment_type == "overall")
    assert overall.factor == pytest.approx(1.3333333333333333)
    assert overall.sample_size == 3
    assert overall.computed_at == _COMPUTED_AT


def test_segments_under_min_sample_size_are_skipped(
    make_settled_bet: Callable[..., SettledBet],
) -> None:
    settled_bets = [
        make_settled_bet(fair_probability=0.5, result=BetResult.WON),
        make_settled_bet(fair_probability=0.5, result=BetResult.LOST),
    ]
    service = CorrectionFactorService(min_sample_size=5)
    factors = service.compute_factors(settled_bets, computed_at=_COMPUTED_AT)
    assert factors == []


def test_push_results_excluded_from_sample_size_and_factor(
    make_settled_bet: Callable[..., SettledBet],
) -> None:
    settled_bets = [
        make_settled_bet(fair_probability=0.5, result=BetResult.WON),
        make_settled_bet(fair_probability=0.5, result=BetResult.LOST),
        make_settled_bet(fair_probability=0.9, result=BetResult.PUSH),
    ]
    service = CorrectionFactorService(min_sample_size=2)
    factors = service.compute_factors(settled_bets, computed_at=_COMPUTED_AT)
    overall = next(f for f in factors if f.segment_type == "overall")
    assert overall.sample_size == 2
    assert overall.factor == pytest.approx(1.0)  # observed 0.5 / predicted 0.5


def test_zero_predicted_mean_segment_is_skipped(
    make_settled_bet: Callable[..., SettledBet],
) -> None:
    settled_bets = [
        make_settled_bet(fair_probability=0.0, result=BetResult.LOST),
        make_settled_bet(fair_probability=0.0, result=BetResult.LOST),
    ]
    service = CorrectionFactorService(min_sample_size=2)
    factors = service.compute_factors(settled_bets, computed_at=_COMPUTED_AT)
    assert factors == []


def test_data_range_spans_min_and_max_settled_at(
    make_settled_bet: Callable[..., SettledBet],
) -> None:
    early = datetime(2026, 1, 1, tzinfo=timezone.utc)
    late = datetime(2026, 6, 1, tzinfo=timezone.utc)
    settled_bets = [
        make_settled_bet(fair_probability=0.5, result=BetResult.WON, settled_at=early),
        make_settled_bet(fair_probability=0.5, result=BetResult.LOST, settled_at=late),
    ]
    service = CorrectionFactorService(min_sample_size=2)
    factors = service.compute_factors(settled_bets, computed_at=_COMPUTED_AT)
    overall = next(f for f in factors if f.segment_type == "overall")
    assert overall.data_range_start == early
    assert overall.data_range_end == late


def test_compute_factors_includes_bookmaker_and_prop_type_segments(
    make_settled_bet: Callable[..., SettledBet], betplay: Bookmaker
) -> None:
    settled_bets = [
        make_settled_bet(
            fair_probability=0.5,
            result=BetResult.WON,
            market_type=MarketType.PLAYER_PROP,
            outcome="Lionel Messi SHOTS_ON_TARGET Over",
            bookmaker=betplay,
        ),
        make_settled_bet(
            fair_probability=0.5,
            result=BetResult.LOST,
            market_type=MarketType.PLAYER_PROP,
            outcome="Lionel Messi SHOTS_ON_TARGET Over",
            bookmaker=betplay,
        ),
        make_settled_bet(
            fair_probability=0.5,
            result=BetResult.WON,
            market_type=MarketType.PLAYER_PROP,
            outcome="Lionel Messi UNKNOWN_METRIC Over",
            bookmaker=betplay,
        ),
    ]
    service = CorrectionFactorService(min_sample_size=2)
    factors = service.compute_factors(settled_bets, computed_at=_COMPUTED_AT)

    segments = {(f.segment_type, f.segment_value) for f in factors}
    assert ("bookmaker", "Betplay") in segments
    assert ("prop_type", "SHOTS_ON_TARGET") in segments


def test_min_sample_size_must_be_at_least_one() -> None:
    with pytest.raises(ValueError):
        CorrectionFactorService(min_sample_size=0)


def test_apply_correction_factor_hand_derived() -> None:
    factor = CorrectionFactor(
        segment_type="overall",
        segment_value="overall",
        factor=1.2,
        sample_size=10,
        computed_at=_COMPUTED_AT,
        data_range_start=_COMPUTED_AT,
        data_range_end=_COMPUTED_AT,
    )
    assert apply_correction_factor(Probability(0.5), factor).value == pytest.approx(0.6)


def test_apply_correction_factor_clamps_to_one() -> None:
    factor = CorrectionFactor(
        segment_type="overall",
        segment_value="overall",
        factor=1.5,
        sample_size=10,
        computed_at=_COMPUTED_AT,
        data_range_start=_COMPUTED_AT,
        data_range_end=_COMPUTED_AT,
    )
    assert apply_correction_factor(Probability(0.9), factor).value == 1.0


@pytest.mark.parametrize("factor_value", [0.0, -1.0])
def test_correction_factor_requires_positive_factor(factor_value: float) -> None:
    with pytest.raises(ValueError):
        CorrectionFactor(
            segment_type="overall",
            segment_value="overall",
            factor=factor_value,
            sample_size=10,
            computed_at=_COMPUTED_AT,
            data_range_start=_COMPUTED_AT,
            data_range_end=_COMPUTED_AT,
        )


def test_correction_factor_requires_non_negative_sample_size() -> None:
    with pytest.raises(ValueError):
        CorrectionFactor(
            segment_type="overall",
            segment_value="overall",
            factor=1.0,
            sample_size=-1,
            computed_at=_COMPUTED_AT,
            data_range_start=_COMPUTED_AT,
            data_range_end=_COMPUTED_AT,
        )


def test_correction_factor_requires_timezone_aware_datetimes() -> None:
    with pytest.raises(ValueError):
        CorrectionFactor(
            segment_type="overall",
            segment_value="overall",
            factor=1.0,
            sample_size=10,
            computed_at=datetime(2026, 9, 1),
            data_range_start=_COMPUTED_AT,
            data_range_end=_COMPUTED_AT,
        )


def test_correction_factor_requires_utc_datetimes() -> None:
    non_utc = timezone(timedelta(hours=-3))
    with pytest.raises(ValueError):
        CorrectionFactor(
            segment_type="overall",
            segment_value="overall",
            factor=1.0,
            sample_size=10,
            computed_at=datetime(2026, 9, 1, tzinfo=non_utc),
            data_range_start=_COMPUTED_AT,
            data_range_end=_COMPUTED_AT,
        )


def test_correction_factor_requires_data_range_start_before_end() -> None:
    with pytest.raises(ValueError):
        CorrectionFactor(
            segment_type="overall",
            segment_value="overall",
            factor=1.0,
            sample_size=10,
            computed_at=_COMPUTED_AT,
            data_range_start=datetime(2026, 6, 1, tzinfo=timezone.utc),
            data_range_end=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def test_latest_by_segment_keeps_most_recent_computed_at() -> None:
    older = CorrectionFactor(
        segment_type="overall",
        segment_value="overall",
        factor=1.0,
        sample_size=10,
        computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        data_range_start=_COMPUTED_AT,
        data_range_end=_COMPUTED_AT,
    )
    newer = CorrectionFactor(
        segment_type="overall",
        segment_value="overall",
        factor=1.1,
        sample_size=20,
        computed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        data_range_start=_COMPUTED_AT,
        data_range_end=_COMPUTED_AT,
    )
    other_segment = CorrectionFactor(
        segment_type="market_type",
        segment_value="OVER_UNDER",
        factor=0.9,
        sample_size=15,
        computed_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        data_range_start=_COMPUTED_AT,
        data_range_end=_COMPUTED_AT,
    )
    result = latest_by_segment([older, newer, other_segment])
    assert len(result) == 2
    assert newer in result
    assert older not in result
    assert other_segment in result


def test_latest_by_segment_ignores_an_earlier_factor_seen_after_a_later_one() -> None:
    newer = CorrectionFactor(
        segment_type="overall",
        segment_value="overall",
        factor=1.1,
        sample_size=20,
        computed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        data_range_start=_COMPUTED_AT,
        data_range_end=_COMPUTED_AT,
    )
    older = CorrectionFactor(
        segment_type="overall",
        segment_value="overall",
        factor=1.0,
        sample_size=10,
        computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        data_range_start=_COMPUTED_AT,
        data_range_end=_COMPUTED_AT,
    )
    result = latest_by_segment([newer, older])
    assert result == [newer]
