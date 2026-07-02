"""Devig strategy tests.

Hand-computed vectors, derived independently of the implementation:

- Asymmetric market (Pinnacle 2.00 / 3.40 / 4.00): raw implied probabilities
  are exact fractions (1/2, 5/17, 1/4) summing to 71/68 * ... -> working in
  exact rationals, multiplicative fair probs are 34/71, 20/71, 17/71 and
  additive fair probs are 33/68, 19/68, 16/68 (see module comment below for
  the derivation). These give closed-form expected values for the two
  strategies that have one.
- No-vig market (raw implied probabilities already sum to 1.0): every
  strategy is a no-op by construction (there is no margin to remove), so all
  four must agree exactly with the raw implied probabilities - this doubles
  as a hand-verifiable vector for Shin and Power, which have no closed form
  for the general (asymmetric, overround) case.
- Symmetric market with overround (identical odds on every outcome): by
  symmetry the fair split must be exactly 1/n for every strategy, regardless
  of method-specific math - a second hand-verifiable vector for Shin/Power.

Derivation for the asymmetric vector (exact fractions):
  raw = (1/2, 5/17, 1/4), sum = 0.75 + 5/17 = (12.75 + 5)/17 = 17.75/17
  multiplicative: p_i = raw_i / sum -> (0.5*17/17.75, (5/17)*17/17.75, 0.25*17/17.75)
                       = (8.5/17.75, 5/17.75, 4.25/17.75) = (34/71, 20/71, 17/71)
  additive: overround = 17.75/17 - 1 = 3/68; share = 1/68
            p_i = raw_i - 1/68 -> (33/68, 19/68, 16/68)
"""

import math

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from src.domain.services.market_model.devig import (
    AdditiveDevig,
    DevigStrategy,
    MultiplicativeDevig,
    PowerDevig,
    ShinDevig,
)
from src.domain.value_objects.decimal_odds import DecimalOdds

ALL_STRATEGIES = [MultiplicativeDevig(), AdditiveDevig(), ShinDevig(), PowerDevig()]
STRATEGY_IDS = ["multiplicative", "additive", "shin", "power"]

ASYMMETRIC_ODDS = [DecimalOdds(2.00), DecimalOdds(3.40), DecimalOdds(4.00)]


# --- Multiplicative: exact hand-derived vector -------------------------------


def test_multiplicative_matches_hand_derived_fractions() -> None:
    probs = MultiplicativeDevig().devig(ASYMMETRIC_ODDS)

    assert probs[0].value == pytest.approx(34 / 71)
    assert probs[1].value == pytest.approx(20 / 71)
    assert probs[2].value == pytest.approx(17 / 71)
    assert sum(p.value for p in probs) == pytest.approx(1.0)


# --- Additive: exact hand-derived vector -------------------------------------


def test_additive_matches_hand_derived_fractions() -> None:
    probs = AdditiveDevig().devig(ASYMMETRIC_ODDS)

    assert probs[0].value == pytest.approx(33 / 68)
    assert probs[1].value == pytest.approx(19 / 68)
    assert probs[2].value == pytest.approx(16 / 68)
    assert sum(p.value for p in probs) == pytest.approx(1.0)


# --- Cross-strategy hand-verifiable vectors (no-vig, symmetric) -------------


@pytest.mark.parametrize("strategy", ALL_STRATEGIES, ids=STRATEGY_IDS)
def test_no_vig_market_is_a_no_op_for_every_strategy(strategy: DevigStrategy) -> None:
    """Raw implied probabilities already sum to 1.0 (odds 2.00/2.00, a fair
    coin-flip market with zero margin) - there is no overround for any
    method to remove, so every strategy must return the raw probabilities
    unchanged."""
    probs = strategy.devig([DecimalOdds(2.00), DecimalOdds(2.00)])

    assert probs[0].value == pytest.approx(0.5)
    assert probs[1].value == pytest.approx(0.5)


@pytest.mark.parametrize("strategy", ALL_STRATEGIES, ids=STRATEGY_IDS)
def test_symmetric_market_with_overround_splits_evenly_for_every_strategy(
    strategy: DevigStrategy,
) -> None:
    """Three identical odds (2.85/2.85/2.85, ~5.3% overround): by symmetry
    the fair probability must be exactly 1/3 per outcome for ANY method,
    since nothing distinguishes one outcome from another."""
    probs = strategy.devig([DecimalOdds(2.85)] * 3)

    for prob in probs:
        assert prob.value == pytest.approx(1 / 3)


# --- Sum-to-1 across several concrete odds sets ------------------------------


@pytest.mark.parametrize("strategy", ALL_STRATEGIES, ids=STRATEGY_IDS)
@pytest.mark.parametrize(
    "odds_values",
    [
        [2.00, 3.40, 4.00],
        [1.90, 2.05],  # 2-way (e.g. BTTS)
        [1.50, 4.20, 6.50],
        [1.05, 15.0, 25.0],  # heavily skewed favorite/longshot market
    ],
    ids=["1x2-typical", "2-way", "1x2-wide", "skewed"],
)
def test_probabilities_sum_to_one(
    strategy: DevigStrategy, odds_values: list[float]
) -> None:
    probs = strategy.devig([DecimalOdds(v) for v in odds_values])

    assert sum(p.value for p in probs) == pytest.approx(1.0, abs=1e-9)
    for prob in probs:
        assert 0.0 <= prob.value <= 1.0


# --- Error handling -----------------------------------------------------------


@pytest.mark.parametrize("strategy", ALL_STRATEGIES, ids=STRATEGY_IDS)
def test_devig_requires_at_least_two_outcomes(strategy: DevigStrategy) -> None:
    with pytest.raises(ValueError):
        strategy.devig([DecimalOdds(2.00)])


def test_shin_rejects_an_underround_market() -> None:
    """Raw implied probabilities summing to < 1.0 has no z in [0, 1) that
    solves Shin's model - this is a data anomaly the strategy must reject
    rather than silently return nonsense."""
    with pytest.raises(ValueError, match="overround"):
        ShinDevig().devig([DecimalOdds(2.10), DecimalOdds(2.10)])  # raw sum = 0.952...


def test_shin_accepts_the_exact_no_vig_boundary() -> None:
    """Raw implied probabilities summing to exactly 1.0 is the boundary
    z=0 case, not an error."""
    probs = ShinDevig().devig([DecimalOdds(2.00), DecimalOdds(2.00)])
    assert sum(p.value for p in probs) == pytest.approx(1.0)


def test_additive_can_raise_for_a_heavily_skewed_market() -> None:
    """Known limitation of the additive method (see its docstring):
    subtracting an equal absolute share of the overround can push a
    longshot's raw probability negative when one outcome is heavily
    favored. This exact vector was found by the hypothesis property test
    below before being pinned here as a concrete example."""
    with pytest.raises(ValueError):
        AdditiveDevig().devig([DecimalOdds(2.0), DecimalOdds(5.0), DecimalOdds(1.0625)])


# --- Property-based tests (hypothesis) ---------------------------------------

# Realistic decimal odds for a football match market: never at/below 1.0
# (DecimalOdds' own invariant), rarely above ~15 in practice.
_odds_value = st.floats(min_value=1.05, max_value=15.0, allow_nan=False, allow_infinity=False)
_odds_list = st.lists(_odds_value, min_size=2, max_size=5)


@pytest.mark.parametrize("strategy", ALL_STRATEGIES, ids=STRATEGY_IDS)
@given(odds_values=_odds_list)
def test_property_probabilities_are_in_unit_interval_and_sum_to_one(
    strategy: DevigStrategy, odds_values: list[float]
) -> None:
    if isinstance(strategy, ShinDevig):
        assume(sum(1.0 / v for v in odds_values) >= 1.0)

    try:
        probs = strategy.devig([DecimalOdds(v) for v in odds_values])
    except ValueError:
        # Additive's documented failure mode: a heavily skewed market can
        # push a longshot's share negative. Multiplicative/Shin/Power are
        # mathematically guaranteed never to raise here (see their
        # docstrings) - only additive gets this escape hatch.
        assert isinstance(strategy, AdditiveDevig)
        return

    for prob in probs:
        assert 0.0 <= prob.value <= 1.0
    assert sum(p.value for p in probs) == pytest.approx(1.0, abs=1e-6)


@given(odds_values=_odds_list)
def test_property_multiplicative_and_additive_agree_when_market_is_symmetric(
    odds_values: list[float],
) -> None:
    """A hypothesis-driven generalization of the hand-verified symmetric
    vector: whatever the common odds value and outcome count, every
    strategy must split fair probability evenly."""
    n = len(odds_values)
    odds = [DecimalOdds(odds_values[0])] * n

    for strategy in (MultiplicativeDevig(), AdditiveDevig()):
        probs = strategy.devig(odds)
        for prob in probs:
            assert prob.value == pytest.approx(1.0 / n)


@given(
    odds_values=_odds_list,
)
def test_property_power_method_always_finds_a_root_within_bounds(
    odds_values: list[float],
) -> None:
    """Power's k is solved by bisection over a fixed bracket - this checks
    the bracket is wide enough for the realistic odds range above."""
    probs = PowerDevig().devig([DecimalOdds(v) for v in odds_values])
    assert sum(p.value for p in probs) == pytest.approx(1.0, abs=1e-6)
    assert all(not math.isnan(p.value) for p in probs)
