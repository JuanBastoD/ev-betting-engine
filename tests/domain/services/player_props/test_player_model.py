"""player_model.py tests.

Hand-computed vectors (matching the prompt's own example: a player
averaging 2.0 shots on target -> P(Over 1.5)):
  lambda=2.0 (rate=2.0, expected_minutes=90, opponent_factor=1.0):
    P(Over 1.5) = P(X>=2) = 1 - (Poisson(0;2)+Poisson(1;2)) = 1 - 3*e^-2 = 0.593994...
  lambda=1.0 (expected_minutes=45, half the baseline):
    P(Over 1.5) = 1 - 2*e^-1 = 0.264241...
  lambda=3.0 (opponent_strength_factor=1.5):
    P(Over 1.5) = 1 - 4*e^-3 = 0.800852...

EWMA vector (alpha=0.5, two matches, most-recent-first: 4 SOT then 0 SOT,
both 90 minutes -> per-90 rates 4.0 and 0.0):
  weights = [0.5, 0.25], sum=0.75 -> rate = (0.5*4 + 0.25*0)/0.75 = 8/3 = 2.6667
  (a plain average would give 2.0 - this is the property that distinguishes
  EWMA from a simple average, exactly what the prompt asks to verify).

Confidence blend vector: model_probability=0.6, odds=2.0, confidence=0.5:
  breakeven = 1/2.0 = 0.5 -> effective = 0.5*0.6 + 0.5*0.5 = 0.55
  (full-confidence edge 0.6*2-1=20%; confidence=0.5 exactly halves it to
  0.55*2-1=10%, matching "reduce the EV by 50%").
"""

import math
from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.domain.entities.injury_status_type import InjuryStatusType
from src.domain.entities.league import League
from src.domain.entities.lineup_confirmation import LineupConfirmation
from src.domain.entities.match import Match
from src.domain.entities.player import Player
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_position import PlayerPosition
from src.domain.entities.player_prop_type import PlayerPropType
from src.domain.entities.team import Team
from src.domain.services.match_model.team_strength import TeamStrength
from src.domain.services.player_props.player_model import (
    MLPropsModel,
    PlayerPropsModel,
    PoissonPropsModel,
    TrainablePropsModel,
    _ewma_per_90_rate,
    confidence_adjusted_probability,
    confidence_penalty,
    expected_minutes_from_lineup,
    opponent_factor_from_team_strength,
)
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.probability import Probability


# --- Hand-derived Poisson vectors ---------------------------------------------


def test_over_probability_matches_the_hand_derived_poisson_formula(
    make_stats: Callable[..., PlayerMatchStats],
) -> None:
    stats = [make_stats(minutes_played=90, shots_on_target=2) for _ in range(3)]
    model = PoissonPropsModel()

    probability = model.predict_probability(
        historical_stats=stats,
        prop_type=PlayerPropType.SHOTS_ON_TARGET,
        outcome="Over",
        line=1.5,
        expected_minutes=90,
    )

    assert probability.value == pytest.approx(1.0 - 3.0 * math.exp(-2.0))


def test_under_probability_is_the_complement(make_stats: Callable[..., PlayerMatchStats]) -> None:
    stats = [make_stats(minutes_played=90, shots_on_target=2) for _ in range(3)]
    model = PoissonPropsModel()

    over = model.predict_probability(
        historical_stats=stats,
        prop_type=PlayerPropType.SHOTS_ON_TARGET,
        outcome="Over",
        line=1.5,
        expected_minutes=90,
    )
    under = model.predict_probability(
        historical_stats=stats,
        prop_type=PlayerPropType.SHOTS_ON_TARGET,
        outcome="Under",
        line=1.5,
        expected_minutes=90,
    )

    assert under.value == pytest.approx(1.0 - over.value)


def test_expected_minutes_scales_the_rate_proportionally(
    make_stats: Callable[..., PlayerMatchStats],
) -> None:
    """Half the baseline minutes (45 of 90) halves lambda: 2.0 -> 1.0."""
    stats = [make_stats(minutes_played=90, shots_on_target=2) for _ in range(3)]
    model = PoissonPropsModel()

    probability = model.predict_probability(
        historical_stats=stats,
        prop_type=PlayerPropType.SHOTS_ON_TARGET,
        outcome="Over",
        line=1.5,
        expected_minutes=45,
    )

    assert probability.value == pytest.approx(1.0 - 2.0 * math.exp(-1.0))


def test_opponent_strength_factor_scales_the_rate(
    make_stats: Callable[..., PlayerMatchStats],
) -> None:
    """opponent_strength_factor=1.5 scales lambda from 2.0 to 3.0."""
    stats = [make_stats(minutes_played=90, shots_on_target=2) for _ in range(3)]
    model = PoissonPropsModel()

    probability = model.predict_probability(
        historical_stats=stats,
        prop_type=PlayerPropType.SHOTS_ON_TARGET,
        outcome="Over",
        line=1.5,
        expected_minutes=90,
        opponent_strength_factor=1.5,
    )

    assert probability.value == pytest.approx(1.0 - 4.0 * math.exp(-3.0))


@pytest.mark.parametrize(
    ("prop_type", "field", "value"),
    [
        (PlayerPropType.GOALS, "goals", 3),
        (PlayerPropType.SHOTS_ON_TARGET, "shots_on_target", 3),
        (PlayerPropType.ASSISTS, "assists", 3),
    ],
)
def test_prop_type_selects_the_matching_stat_field(
    make_stats: Callable[..., PlayerMatchStats], prop_type: PlayerPropType, field: str, value: int
) -> None:
    stats = [make_stats(minutes_played=90, **{field: value}) for _ in range(3)]
    model = PoissonPropsModel()

    probability = model.predict_probability(
        historical_stats=stats, prop_type=prop_type, outcome="Over", line=1.5, expected_minutes=90
    )
    # rate=3.0 per 90 -> lambda=3.0, same closed form as the opponent-factor vector.
    assert probability.value == pytest.approx(1.0 - 4.0 * math.exp(-3.0))


def test_cards_prop_type_sums_yellow_and_red(make_stats: Callable[..., PlayerMatchStats]) -> None:
    stats = [make_stats(minutes_played=90, yellow_cards=1, red_cards=0) for _ in range(3)]
    model = PoissonPropsModel()

    probability = model.predict_probability(
        historical_stats=stats,
        prop_type=PlayerPropType.CARDS,
        outcome="Over",
        line=0.5,
        expected_minutes=90,
    )
    # rate=1.0 per 90 -> lambda=1.0 -> P(Over 0.5) = P(X>=1) = 1-e^-1.
    assert probability.value == pytest.approx(1.0 - math.exp(-1.0))


# --- EWMA recency weighting ----------------------------------------------------


def test_ewma_weights_recent_matches_more_than_a_plain_average_would(
    make_stats: Callable[..., PlayerMatchStats],
) -> None:
    stats_most_recent_first = [
        make_stats(minutes_played=90, shots_on_target=4),
        make_stats(minutes_played=90, shots_on_target=0),
    ]

    rate = _ewma_per_90_rate(stats_most_recent_first, PlayerPropType.SHOTS_ON_TARGET, alpha=0.5)

    assert rate == pytest.approx(8.0 / 3.0)
    assert rate != pytest.approx(2.0)  # a plain average of 4 and 0 would give 2.0


def test_ewma_alpha_of_one_uses_only_the_most_recent_match(
    make_stats: Callable[..., PlayerMatchStats],
) -> None:
    stats_most_recent_first = [
        make_stats(minutes_played=90, shots_on_target=4),
        make_stats(minutes_played=90, shots_on_target=0),
    ]

    rate = _ewma_per_90_rate(stats_most_recent_first, PlayerPropType.SHOTS_ON_TARGET, alpha=1.0)

    assert rate == pytest.approx(4.0)


def test_ewma_excludes_matches_with_zero_minutes_played(
    make_stats: Callable[..., PlayerMatchStats],
) -> None:
    stats = [
        make_stats(minutes_played=90, shots_on_target=2),
        make_stats(minutes_played=0, shots_on_target=0),
    ]

    rate = _ewma_per_90_rate(stats, PlayerPropType.SHOTS_ON_TARGET, alpha=0.5)

    assert rate == pytest.approx(2.0)  # the unplayed match contributes nothing, not a 0 rate


def test_ewma_raises_when_no_usable_matches_exist(
    make_stats: Callable[..., PlayerMatchStats],
) -> None:
    with pytest.raises(ValueError):
        _ewma_per_90_rate([], PlayerPropType.SHOTS_ON_TARGET, alpha=0.5)

    with pytest.raises(ValueError):
        _ewma_per_90_rate(
            [make_stats(minutes_played=0)], PlayerPropType.SHOTS_ON_TARGET, alpha=0.5
        )


# --- Expected minutes from lineup confirmation --------------------------------


def test_expected_minutes_with_no_lineup_confirmation_assumes_a_full_match() -> None:
    assert expected_minutes_from_lineup(None) == pytest.approx(90.0)


def test_expected_minutes_for_a_confirmed_starter_is_the_full_match(
    match: Match, player: Player
) -> None:
    confirmation = LineupConfirmation(
        player=player, match=match, is_starting=True, is_confirmed=True,
        start_probability=Probability(1.0),
    )
    assert expected_minutes_from_lineup(confirmation) == pytest.approx(90.0)


def test_expected_minutes_for_a_confirmed_non_starter_is_bench_minutes(
    match: Match, player: Player
) -> None:
    confirmation = LineupConfirmation(
        player=player, match=match, is_starting=False, is_confirmed=True,
        start_probability=Probability(0.0),
    )
    assert expected_minutes_from_lineup(confirmation) == pytest.approx(15.0)


def test_expected_minutes_interpolates_for_an_unconfirmed_estimate(
    match: Match, player: Player
) -> None:
    confirmation = LineupConfirmation(
        player=player, match=match, is_starting=True, is_confirmed=False,
        start_probability=Probability(0.6),
    )
    # 0.6*90 + 0.4*15 = 54+6=60
    assert expected_minutes_from_lineup(confirmation) == pytest.approx(60.0)


def test_expected_minutes_bench_and_full_match_minutes_are_configurable(
    match: Match, player: Player
) -> None:
    confirmation = LineupConfirmation(
        player=player, match=match, is_starting=False, is_confirmed=True,
        start_probability=Probability(0.0),
    )
    assert expected_minutes_from_lineup(
        confirmation, full_match_minutes=80.0, bench_minutes=20.0
    ) == pytest.approx(20.0)


# --- Confidence penalty ---------------------------------------------------------


def test_confirmed_and_fit_has_no_penalty() -> None:
    assert confidence_penalty(
        lineup_confirmed=True, player_status=InjuryStatusType.FIT
    ) == pytest.approx(1.0)


def test_unconfirmed_lineup_applies_its_penalty() -> None:
    penalty = confidence_penalty(
        lineup_confirmed=False,
        player_status=InjuryStatusType.FIT,
        unconfirmed_lineup_penalty=0.5,
    )
    assert penalty == pytest.approx(0.5)


@pytest.mark.parametrize(
    "status", [InjuryStatusType.DOUBTFUL, InjuryStatusType.INJURED, InjuryStatusType.SUSPENDED]
)
def test_doubtful_or_injured_or_suspended_applies_its_penalty(status: InjuryStatusType) -> None:
    penalty = confidence_penalty(
        lineup_confirmed=True, player_status=status, doubtful_or_injured_penalty=0.4
    )
    assert penalty == pytest.approx(0.6)


def test_both_penalties_compound_multiplicatively() -> None:
    penalty = confidence_penalty(
        lineup_confirmed=False,
        player_status=InjuryStatusType.DOUBTFUL,
        unconfirmed_lineup_penalty=0.5,
        doubtful_or_injured_penalty=0.4,
    )
    assert penalty == pytest.approx(0.5 * 0.6)


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_unconfirmed_lineup_penalty_out_of_range_raises(value: float) -> None:
    with pytest.raises(ValueError):
        confidence_penalty(
            lineup_confirmed=False, player_status=InjuryStatusType.FIT, unconfirmed_lineup_penalty=value
        )


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_doubtful_or_injured_penalty_out_of_range_raises(value: float) -> None:
    with pytest.raises(ValueError):
        confidence_penalty(
            lineup_confirmed=True, player_status=InjuryStatusType.FIT, doubtful_or_injured_penalty=value
        )


# --- Confidence-adjusted probability --------------------------------------------


def test_confidence_adjusted_probability_matches_the_hand_derived_blend() -> None:
    effective = confidence_adjusted_probability(
        model_probability=Probability(0.6), local_odds=DecimalOdds(2.0), confidence=0.5
    )
    assert effective.value == pytest.approx(0.55)


def test_full_confidence_keeps_the_model_probability_unchanged() -> None:
    effective = confidence_adjusted_probability(
        model_probability=Probability(0.6), local_odds=DecimalOdds(2.0), confidence=1.0
    )
    assert effective.value == pytest.approx(0.6)


def test_zero_confidence_collapses_to_the_breakeven_probability() -> None:
    effective = confidence_adjusted_probability(
        model_probability=Probability(0.6), local_odds=DecimalOdds(2.0), confidence=0.0
    )
    assert effective.value == pytest.approx(0.5)


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_confidence_out_of_range_raises(value: float) -> None:
    with pytest.raises(ValueError):
        confidence_adjusted_probability(
            model_probability=Probability(0.6), local_odds=DecimalOdds(2.0), confidence=value
        )


# --- Opponent factor from TeamStrength ------------------------------------------


def test_opponent_factor_from_team_strength_reuses_defense_directly() -> None:
    team = Team(id="t", name="T")
    strength = TeamStrength(team=team, attack=1.0, defense=1.3)

    assert opponent_factor_from_team_strength(strength) == pytest.approx(1.3)


# --- Validation ------------------------------------------------------------------


def test_line_must_be_positive(make_stats: Callable[..., PlayerMatchStats]) -> None:
    stats = [make_stats(minutes_played=90, shots_on_target=2)]
    with pytest.raises(ValueError):
        PoissonPropsModel().predict_probability(
            historical_stats=stats, prop_type=PlayerPropType.SHOTS_ON_TARGET, outcome="Over",
            line=0.0, expected_minutes=90,
        )


def test_expected_minutes_must_not_be_negative(make_stats: Callable[..., PlayerMatchStats]) -> None:
    stats = [make_stats(minutes_played=90, shots_on_target=2)]
    with pytest.raises(ValueError):
        PoissonPropsModel().predict_probability(
            historical_stats=stats, prop_type=PlayerPropType.SHOTS_ON_TARGET, outcome="Over",
            line=1.5, expected_minutes=-1.0,
        )


def test_opponent_strength_factor_must_not_be_negative(
    make_stats: Callable[..., PlayerMatchStats]
) -> None:
    stats = [make_stats(minutes_played=90, shots_on_target=2)]
    with pytest.raises(ValueError):
        PoissonPropsModel().predict_probability(
            historical_stats=stats, prop_type=PlayerPropType.SHOTS_ON_TARGET, outcome="Over",
            line=1.5, expected_minutes=90, opponent_strength_factor=-0.1,
        )


def test_outcome_must_be_over_or_under(make_stats: Callable[..., PlayerMatchStats]) -> None:
    stats = [make_stats(minutes_played=90, shots_on_target=2)]
    with pytest.raises(ValueError):
        PoissonPropsModel().predict_probability(
            historical_stats=stats, prop_type=PlayerPropType.SHOTS_ON_TARGET, outcome="Maybe",
            line=1.5, expected_minutes=90,
        )


def test_unsupported_prop_type_raises(make_stats: Callable[..., PlayerMatchStats]) -> None:
    from types import SimpleNamespace

    from src.domain.services.player_props.player_model import _metric_value

    stats = make_stats(minutes_played=90, shots_on_target=2)
    with pytest.raises(ValueError):
        _metric_value(stats, SimpleNamespace(value="CORNERS"))


@pytest.mark.parametrize("alpha", [0.0, 1.5])
def test_ewma_alpha_out_of_range_raises(alpha: float) -> None:
    with pytest.raises(ValueError):
        PoissonPropsModel(ewma_alpha=alpha)


def test_minutes_baseline_must_be_positive() -> None:
    with pytest.raises(ValueError):
        PoissonPropsModel(minutes_baseline=0.0)


def test_player_props_model_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        PlayerPropsModel()


def test_trainable_props_model_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        TrainablePropsModel()


def test_trainable_props_model_is_a_player_props_model() -> None:
    assert issubclass(TrainablePropsModel, PlayerPropsModel)


def test_ml_props_model_fit_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        MLPropsModel().fit([])


def test_ml_props_model_version_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        _ = MLPropsModel().model_version


def test_ml_props_model_predict_probability_raises_not_implemented(
    make_stats: Callable[..., PlayerMatchStats],
) -> None:
    stats = [make_stats(minutes_played=90, shots_on_target=2)]
    with pytest.raises(NotImplementedError):
        MLPropsModel().predict_probability(
            historical_stats=stats,
            prop_type=PlayerPropType.SHOTS_ON_TARGET,
            outcome="Over",
            line=1.5,
            expected_minutes=90,
        )


# --- Property-based tests (hypothesis) ------------------------------------------

_rate = st.floats(min_value=0.0, max_value=8.0, allow_nan=False)
_minutes = st.floats(min_value=0.0, max_value=120.0, allow_nan=False)
_opponent_factor = st.floats(min_value=0.0, max_value=3.0, allow_nan=False)
_line = st.floats(min_value=0.1, max_value=10.0, allow_nan=False)

# Hypothesis flags function-scoped pytest fixtures under @given (not reset
# between generated examples) - these entities are immutable/side-effect-free,
# so plain module constants sidestep that safely.
_TEAM = Team(id="team-1", name="River Plate")
_MATCH = Match(
    id="match-1",
    home_team=_TEAM,
    away_team=Team(id="team-2", name="Boca Juniors"),
    league=League(id="l", name="Liga"),
    kickoff_utc=datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc),
)
_PLAYER = Player(id="player-1", name="Carlos Bacca", team=_TEAM, position=PlayerPosition.FORWARD)


def _module_stats(*, shots_on_target: int) -> PlayerMatchStats:
    return PlayerMatchStats(
        match=_MATCH, player=_PLAYER, minutes_played=90, started=True,
        shots_total=shots_on_target + 2, shots_on_target=shots_on_target, goals=0, assists=0,
        yellow_cards=0, red_cards=0,
    )


@given(rate=_rate, minutes=_minutes, opponent_factor=_opponent_factor, line=_line)
def test_property_probability_is_always_in_unit_interval(
    rate: float, minutes: float, opponent_factor: float, line: float
) -> None:
    stats = [_module_stats(shots_on_target=round(rate))]
    model = PoissonPropsModel()

    over = model.predict_probability(
        historical_stats=stats, prop_type=PlayerPropType.SHOTS_ON_TARGET, outcome="Over",
        line=line, expected_minutes=minutes, opponent_strength_factor=opponent_factor,
    )
    under = model.predict_probability(
        historical_stats=stats, prop_type=PlayerPropType.SHOTS_ON_TARGET, outcome="Under",
        line=line, expected_minutes=minutes, opponent_strength_factor=opponent_factor,
    )

    assert 0.0 <= over.value <= 1.0
    assert 0.0 <= under.value <= 1.0
    assert over.value + under.value == pytest.approx(1.0, abs=1e-9)


@given(
    model_probability=st.floats(min_value=0.5, max_value=0.999, allow_nan=False),
    odds=st.floats(min_value=1.01, max_value=3.0, allow_nan=False),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_property_lower_confidence_never_increases_a_positive_edge(
    model_probability: float, odds: float, confidence: float
) -> None:
    """Scoped to a genuinely positive raw edge (model_probability > 1/odds,
    i.e. breakeven) - the economically meaningful case for a +EV detector.
    Below breakeven, the same blend moves the (already-losing) edge toward
    zero from the other direction, which is not what this invariant is
    about (such a bet never clears a positive EV threshold either way)."""
    from hypothesis import assume

    breakeven = 1.0 / odds
    assume(model_probability > breakeven)

    from src.domain.services.player_props.prop_ev_calculator import calculate_ev

    full_confidence_probability = confidence_adjusted_probability(
        model_probability=Probability(model_probability),
        local_odds=DecimalOdds(odds),
        confidence=1.0,
    )
    reduced_confidence_probability = confidence_adjusted_probability(
        model_probability=Probability(model_probability),
        local_odds=DecimalOdds(odds),
        confidence=confidence,
    )

    full_edge = calculate_ev(fair_probability=full_confidence_probability, local_odds=DecimalOdds(odds))
    reduced_edge = calculate_ev(
        fair_probability=reduced_confidence_probability, local_odds=DecimalOdds(odds)
    )

    assert reduced_edge.value <= full_edge.value + 1e-9
