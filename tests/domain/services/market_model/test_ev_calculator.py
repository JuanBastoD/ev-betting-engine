import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.domain.services.market_model.ev_calculator import (
    breakeven_odds,
    calculate_ev,
    exceeds_ev_threshold,
)
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.edge_percentage import EdgePercentage
from src.domain.value_objects.probability import Probability


def test_clearly_positive_ev() -> None:
    edge = calculate_ev(fair_probability=Probability(0.5), local_odds=DecimalOdds(2.20))

    assert edge.value == pytest.approx(10.0)
    assert edge.is_positive_ev is True


def test_neutral_ev_at_exact_breakeven_odds() -> None:
    edge = calculate_ev(fair_probability=Probability(0.5), local_odds=DecimalOdds(2.00))

    assert edge.value == pytest.approx(0.0)
    assert edge.is_positive_ev is False


def test_clearly_negative_ev() -> None:
    edge = calculate_ev(fair_probability=Probability(0.5), local_odds=DecimalOdds(1.80))

    assert edge.value == pytest.approx(-10.0)
    assert edge.is_positive_ev is False


def test_breakeven_odds_is_the_inverse_of_fair_probability() -> None:
    assert breakeven_odds(Probability(0.5)) == pytest.approx(2.0)
    assert breakeven_odds(Probability(0.25)) == pytest.approx(4.0)


@pytest.mark.parametrize(
    ("fair_probability", "local_odds", "expected"),
    [
        (0.5, 2.20, True),  # 2.20 > breakeven 2.00 -> +EV
        (0.5, 2.00, False),  # exactly breakeven -> not +EV
        (0.5, 1.80, False),  # below breakeven -> -EV
    ],
)
def test_positive_ev_matches_the_odds_exceeds_breakeven_definition(
    fair_probability: float, local_odds: float, expected: bool
) -> None:
    edge = calculate_ev(
        fair_probability=Probability(fair_probability), local_odds=DecimalOdds(local_odds)
    )
    assert (local_odds > breakeven_odds(Probability(fair_probability))) == expected
    assert edge.is_positive_ev == expected


def test_exceeds_ev_threshold_filters_by_the_configured_minimum() -> None:
    edge = EdgePercentage(2.5)

    assert exceeds_ev_threshold(edge, min_ev_threshold=0.02) is True  # 2.5% > 2%
    assert exceeds_ev_threshold(edge, min_ev_threshold=0.03) is False  # 2.5% < 3%


def test_exceeds_ev_threshold_is_a_strict_inequality() -> None:
    edge = EdgePercentage(2.0)

    assert exceeds_ev_threshold(edge, min_ev_threshold=0.02) is False  # exactly at the bar


# --- Property-based tests (hypothesis) ---------------------------------------

_probability = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_odds_value = st.floats(min_value=1.0001, max_value=100.0, allow_nan=False, allow_infinity=False)


@given(probability=_probability, odds=_odds_value)
def test_property_calculate_ev_never_violates_the_edge_percentage_floor(
    probability: float, odds: float
) -> None:
    """p*odds - 1 >= -1 always (p>=0, odds>0), i.e. EdgePercentage's -100.0
    floor is never breached - calculate_ev must never raise."""
    edge = calculate_ev(fair_probability=Probability(probability), local_odds=DecimalOdds(odds))
    assert edge.value >= -100.0


@given(probability=st.floats(min_value=0.01, max_value=1.0, allow_nan=False), odds=_odds_value)
def test_property_positive_ev_iff_odds_exceed_breakeven(probability: float, odds: float) -> None:
    edge = calculate_ev(fair_probability=Probability(probability), local_odds=DecimalOdds(odds))
    assert edge.is_positive_ev == (odds > breakeven_odds(Probability(probability)))
