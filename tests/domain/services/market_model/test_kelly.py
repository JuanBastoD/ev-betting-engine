"""Kelly stake-sizing tests.

Hand-computed vectors:
  p=0.55, odds=2.00 -> b=1.0, q=0.45 -> f* = (1*0.55 - 0.45)/1 = 0.10
  p=0.40, odds=2.00 -> b=1.0, q=0.60 -> f* = (1*0.40 - 0.60)/1 = -0.20 (negative)
  p=0.90, odds=3.00 -> b=2.0, q=0.10 -> f* = (2*0.90 - 0.10)/2 = 0.85
  p=0.50, odds=2.00 -> f* = 0 exactly (fair price, zero edge)
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.domain.services.market_model.kelly import kelly_stake
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.probability import Probability


def test_full_kelly_matches_the_hand_derived_fraction() -> None:
    stake = kelly_stake(probability=Probability(0.55), odds=DecimalOdds(2.00), kelly_fraction=1.0)

    assert stake is not None
    assert stake.amount == pytest.approx(0.10)


def test_negative_edge_gives_no_stake() -> None:
    stake = kelly_stake(probability=Probability(0.40), odds=DecimalOdds(2.00), kelly_fraction=1.0)

    assert stake is None


def test_exactly_zero_edge_gives_no_stake() -> None:
    """p equal to the breakeven probability (1/odds) is a fair price: f* = 0
    exactly, which must not become Stake(0.0) - Stake requires amount > 0."""
    stake = kelly_stake(probability=Probability(0.5), odds=DecimalOdds(2.00), kelly_fraction=1.0)

    assert stake is None


@pytest.mark.parametrize(
    ("kelly_fraction", "expected_amount"),
    [
        (1.0, 0.10),  # full Kelly
        (0.5, 0.05),  # half Kelly
        (0.25, 0.025),  # quarter Kelly
    ],
)
def test_kelly_fraction_scales_the_full_kelly_result(
    kelly_fraction: float, expected_amount: float
) -> None:
    stake = kelly_stake(
        probability=Probability(0.55), odds=DecimalOdds(2.00), kelly_fraction=kelly_fraction
    )

    assert stake is not None
    assert stake.amount == pytest.approx(expected_amount)


def test_max_fraction_of_zero_always_gives_no_stake() -> None:
    """A zero cap is a valid (if degenerate) input, not a ValueError: it
    must produce no stake rather than an invalid Stake(0.0)."""
    stake = kelly_stake(
        probability=Probability(0.55),
        odds=DecimalOdds(2.00),
        kelly_fraction=1.0,
        max_fraction=0.0,
    )
    assert stake is None


def test_kelly_fraction_of_zero_always_gives_no_stake() -> None:
    stake = kelly_stake(probability=Probability(0.55), odds=DecimalOdds(2.00), kelly_fraction=0.0)

    assert stake is None


def test_max_fraction_caps_an_aggressive_full_kelly_result() -> None:
    """p=0.90, odds=3.00 -> full Kelly f*=0.85 (very aggressive); capped
    down to the 5% safety ceiling."""
    stake = kelly_stake(
        probability=Probability(0.9),
        odds=DecimalOdds(3.00),
        kelly_fraction=1.0,
        max_fraction=0.05,
    )

    assert stake is not None
    assert stake.amount == pytest.approx(0.05)


def test_max_fraction_does_not_affect_a_result_already_under_the_cap() -> None:
    stake = kelly_stake(
        probability=Probability(0.55),
        odds=DecimalOdds(2.00),
        kelly_fraction=0.25,
        max_fraction=0.05,
    )

    assert stake is not None
    assert stake.amount == pytest.approx(0.025)


@pytest.mark.parametrize("kelly_fraction", [-0.1, 1.1])
def test_kelly_fraction_out_of_range_raises(kelly_fraction: float) -> None:
    with pytest.raises(ValueError):
        kelly_stake(probability=Probability(0.55), odds=DecimalOdds(2.00), kelly_fraction=kelly_fraction)


@pytest.mark.parametrize("max_fraction", [-0.1, 1.1])
def test_max_fraction_out_of_range_raises(max_fraction: float) -> None:
    with pytest.raises(ValueError):
        kelly_stake(
            probability=Probability(0.55),
            odds=DecimalOdds(2.00),
            kelly_fraction=1.0,
            max_fraction=max_fraction,
        )


# --- Property-based tests (hypothesis) ---------------------------------------

_probability = st.floats(min_value=0.001, max_value=0.999, allow_nan=False)
_odds_value = st.floats(min_value=1.01, max_value=50.0, allow_nan=False)
_fraction = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


@given(
    probability=_probability,
    odds=_odds_value,
    kelly_fraction=_fraction,
    max_fraction=_fraction,
)
def test_property_stake_is_never_negative_and_never_exceeds_the_cap(
    probability: float, odds: float, kelly_fraction: float, max_fraction: float
) -> None:
    stake = kelly_stake(
        probability=Probability(probability),
        odds=DecimalOdds(odds),
        kelly_fraction=kelly_fraction,
        max_fraction=max_fraction,
    )

    assert stake is None or (0.0 < stake.amount <= max_fraction)


@given(probability=_probability, odds=_odds_value)
def test_property_zero_kelly_fraction_never_produces_a_stake(
    probability: float, odds: float
) -> None:
    stake = kelly_stake(
        probability=Probability(probability), odds=DecimalOdds(odds), kelly_fraction=0.0
    )
    assert stake is None
