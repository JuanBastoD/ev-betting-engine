"""xg_model.py (Dixon-Coles) tests.

The reference helpers below (`_poisson_pmf`/`_tau`/`_score_probability`) are
a direct, independent transcription of the Dixon & Coles (1997) formula -
not a call into `DixonColesModel` - used to hand-verify individual scoreline
probabilities. They deliberately skip the grid truncation/renormalization
`DixonColesModel` applies (dividing by the sum over the 0..max_goals grid),
whose effect is negligible (~1e-9) for any realistic lambda, so comparing
against these un-normalized reference values with a loose-but-meaningful
tolerance (abs=1e-4) still catches real bugs (e.g. swapping lambda/mu in
tau) while accepting that harmless truncation effect.
"""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.domain.entities.team import Team
from src.domain.services.match_model.team_strength import TeamStrength
from src.domain.services.match_model.xg_model import (
    DixonColesModel,
    MatchStatisticalModel,
    OverUnderProbability,
)


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)


def _tau(x: int, y: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if x == 0 and y == 1:
        return 1.0 + lambda_home * rho
    if x == 1 and y == 0:
        return 1.0 + lambda_away * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def _score_probability(x: int, y: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    return (
        _tau(x, y, lambda_home, lambda_away, rho)
        * _poisson_pmf(x, lambda_home)
        * _poisson_pmf(y, lambda_away)
    )


@pytest.fixture
def home_team() -> Team:
    return Team(id="team-home", name="River Plate")


@pytest.fixture
def away_team() -> Team:
    return Team(id="team-away", name="Boca Juniors")


# --- Hand-derived scoreline vectors -------------------------------------------


def test_specific_scorelines_match_the_dixon_coles_formula(
    home_team: Team, away_team: Team
) -> None:
    """attack_home=1.2, defense_away=1.2, home_advantage=1.5, league_average=1.0
    -> lambda_home = 1.0*1.2*1.2*1.5 = 2.16
    attack_away=0.8, defense_home=0.8 -> lambda_away = 1.0*0.8*0.8 = 0.64
    rho=-0.1.
    """
    home = TeamStrength(team=home_team, attack=1.2, defense=0.8)
    away = TeamStrength(team=away_team, attack=0.8, defense=1.2)
    model = DixonColesModel(home_advantage=1.5, rho=-0.1)

    probabilities = model.predict_match_probabilities(home, away, league_average_goals=1.0)

    lambda_home, lambda_away, rho = 2.16, 0.64, -0.1
    for (x, y) in [(0, 0), (1, 0), (0, 1), (1, 1), (2, 1)]:
        expected = _score_probability(x, y, lambda_home, lambda_away, rho)
        assert probabilities.score_matrix[(x, y)] == pytest.approx(expected, abs=1e-4)


def test_resulting_1x2_matches_a_from_scratch_aggregation_of_the_formula(
    home_team: Team, away_team: Team
) -> None:
    home = TeamStrength(team=home_team, attack=1.2, defense=0.8)
    away = TeamStrength(team=away_team, attack=0.8, defense=1.2)
    model = DixonColesModel(home_advantage=1.5, rho=-0.1, max_goals=10)

    probabilities = model.predict_match_probabilities(home, away, league_average_goals=1.0)

    lambda_home, lambda_away, rho = 2.16, 0.64, -0.1
    raw = {
        (x, y): _score_probability(x, y, lambda_home, lambda_away, rho)
        for x in range(11)
        for y in range(11)
    }
    total = sum(raw.values())
    expected_home_win = sum(p for (x, y), p in raw.items() if x > y) / total
    expected_draw = sum(p for (x, y), p in raw.items() if x == y) / total
    expected_away_win = sum(p for (x, y), p in raw.items() if x < y) / total

    assert probabilities.home_win.value == pytest.approx(expected_home_win, abs=1e-6)
    assert probabilities.draw.value == pytest.approx(expected_draw, abs=1e-6)
    assert probabilities.away_win.value == pytest.approx(expected_away_win, abs=1e-6)


def test_tau_correction_going_negative_is_floored_not_left_negative(
    home_team: Team, away_team: Team
) -> None:
    """attack=2.0/2.0, home_advantage=1.5, league_average_goals=2.0 ->
    lambda_home=12.0; with rho=-0.1, tau(0,1) = 1 + 12*(-0.1) = -0.2, a
    negative "probability" from the raw formula. This exact combination was
    found by the hypothesis property test before being pinned here."""
    home = TeamStrength(team=home_team, attack=2.0, defense=1.0)
    away = TeamStrength(team=away_team, attack=1.0, defense=2.0)
    model = DixonColesModel(home_advantage=1.5, rho=-0.1)

    probabilities = model.predict_match_probabilities(home, away, league_average_goals=2.0)

    for value in probabilities.score_matrix.values():
        assert value >= 0.0
    assert sum(probabilities.score_matrix.values()) == pytest.approx(1.0)


def test_no_correction_reduces_to_plain_independent_poisson(
    home_team: Team, away_team: Team
) -> None:
    """rho=0 turns off the low-score correction entirely (tau=1 always),
    so P(0,0) must equal the plain Poisson product exactly: with
    lambda_home=lambda_away=1.5, that's e^-1.5 * e^-1.5 = e^-3."""
    home = TeamStrength(team=home_team, attack=1.0, defense=1.0)
    away = TeamStrength(team=away_team, attack=1.0, defense=1.0)
    model = DixonColesModel(home_advantage=1.0, rho=0.0)

    probabilities = model.predict_match_probabilities(home, away, league_average_goals=1.5)

    assert probabilities.score_matrix[(0, 0)] == pytest.approx(math.exp(-3.0), abs=1e-6)


# --- Structural invariants -----------------------------------------------------


def test_score_matrix_sums_to_one(home_team: Team, away_team: Team) -> None:
    home = TeamStrength(team=home_team, attack=1.3, defense=0.7)
    away = TeamStrength(team=away_team, attack=0.9, defense=1.1)
    probabilities = DixonColesModel().predict_match_probabilities(
        home, away, league_average_goals=1.4
    )

    assert sum(probabilities.score_matrix.values()) == pytest.approx(1.0)


def test_1x2_sums_to_one(home_team: Team, away_team: Team) -> None:
    home = TeamStrength(team=home_team, attack=1.3, defense=0.7)
    away = TeamStrength(team=away_team, attack=0.9, defense=1.1)
    probabilities = DixonColesModel().predict_match_probabilities(
        home, away, league_average_goals=1.4
    )

    total = probabilities.home_win.value + probabilities.draw.value + probabilities.away_win.value
    assert total == pytest.approx(1.0)


def test_btts_sums_to_one_and_over_under_sums_to_one_per_line(
    home_team: Team, away_team: Team
) -> None:
    home = TeamStrength(team=home_team, attack=1.3, defense=0.7)
    away = TeamStrength(team=away_team, attack=0.9, defense=1.1)
    probabilities = DixonColesModel().predict_match_probabilities(
        home, away, league_average_goals=1.4
    )

    assert probabilities.btts_yes.value + probabilities.btts_no.value == pytest.approx(1.0)
    for entry in probabilities.over_under:
        assert entry.over.value + entry.under.value == pytest.approx(1.0)


def test_default_over_under_lines_are_1_5_2_5_3_5(home_team: Team, away_team: Team) -> None:
    home = TeamStrength(team=home_team, attack=1.0, defense=1.0)
    away = TeamStrength(team=away_team, attack=1.0, defense=1.0)
    probabilities = DixonColesModel().predict_match_probabilities(
        home, away, league_average_goals=1.4
    )

    assert {entry.line for entry in probabilities.over_under} == {1.5, 2.5, 3.5}


def test_over_under_for_line_finds_the_matching_entry(home_team: Team, away_team: Team) -> None:
    home = TeamStrength(team=home_team, attack=1.0, defense=1.0)
    away = TeamStrength(team=away_team, attack=1.0, defense=1.0)
    probabilities = DixonColesModel().predict_match_probabilities(
        home, away, league_average_goals=1.4
    )

    assert probabilities.over_under_for_line(2.5).line == 2.5


def test_over_under_for_an_unconfigured_line_raises(home_team: Team, away_team: Team) -> None:
    home = TeamStrength(team=home_team, attack=1.0, defense=1.0)
    away = TeamStrength(team=away_team, attack=1.0, defense=1.0)
    probabilities = DixonColesModel().predict_match_probabilities(
        home, away, league_average_goals=1.4
    )

    with pytest.raises(ValueError):
        probabilities.over_under_for_line(6.5)


def test_over_under_lines_are_configurable(home_team: Team, away_team: Team) -> None:
    home = TeamStrength(team=home_team, attack=1.0, defense=1.0)
    away = TeamStrength(team=away_team, attack=1.0, defense=1.0)
    model = DixonColesModel(over_under_lines=(0.5,))

    probabilities = model.predict_match_probabilities(home, away, league_average_goals=1.4)

    assert {entry.line for entry in probabilities.over_under} == {0.5}


# --- Error handling / validation -----------------------------------------------


def test_over_under_probability_requires_a_positive_line() -> None:
    from src.domain.value_objects.probability import Probability

    with pytest.raises(ValueError):
        OverUnderProbability(line=0.0, over=Probability(0.5), under=Probability(0.5))


def test_home_advantage_must_be_positive() -> None:
    with pytest.raises(ValueError):
        DixonColesModel(home_advantage=0.0)


def test_max_goals_must_be_at_least_one() -> None:
    with pytest.raises(ValueError):
        DixonColesModel(max_goals=0)


def test_league_average_goals_must_be_positive(home_team: Team, away_team: Team) -> None:
    home = TeamStrength(team=home_team, attack=1.0, defense=1.0)
    away = TeamStrength(team=away_team, attack=1.0, defense=1.0)
    with pytest.raises(ValueError):
        DixonColesModel().predict_match_probabilities(home, away, league_average_goals=0.0)


def test_extreme_strengths_that_underflow_the_grid_raise(
    home_team: Team, away_team: Team
) -> None:
    home = TeamStrength(team=home_team, attack=100.0, defense=100.0)
    away = TeamStrength(team=away_team, attack=100.0, defense=100.0)
    model = DixonColesModel(max_goals=10)

    with pytest.raises(ValueError):
        model.predict_match_probabilities(home, away, league_average_goals=50.0)


def test_match_statistical_model_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        MatchStatisticalModel()


# --- Property-based tests (hypothesis) ---------------------------------------

_strength_value = st.floats(min_value=0.3, max_value=2.0, allow_nan=False)
_league_average = st.floats(min_value=0.8, max_value=2.0, allow_nan=False)
_home_advantage = st.floats(min_value=1.0, max_value=1.6, allow_nan=False)

# Hypothesis flags function-scoped pytest fixtures under @given (not reset
# between generated examples) - Team is immutable/side-effect-free, so a
# plain module constant sidesteps that safely.
_HOME_TEAM = Team(id="team-home", name="River Plate")
_AWAY_TEAM = Team(id="team-away", name="Boca Juniors")


@given(
    home_attack=_strength_value,
    home_defense=_strength_value,
    away_attack=_strength_value,
    away_defense=_strength_value,
    league_average_goals=_league_average,
    home_advantage=_home_advantage,
)
def test_property_probabilities_are_internally_consistent(
    home_attack: float,
    home_defense: float,
    away_attack: float,
    away_defense: float,
    league_average_goals: float,
    home_advantage: float,
) -> None:
    home = TeamStrength(team=_HOME_TEAM, attack=home_attack, defense=home_defense)
    away = TeamStrength(team=_AWAY_TEAM, attack=away_attack, defense=away_defense)
    model = DixonColesModel(home_advantage=home_advantage, rho=-0.1)

    probabilities = model.predict_match_probabilities(
        home, away, league_average_goals=league_average_goals
    )

    assert sum(probabilities.score_matrix.values()) == pytest.approx(1.0, abs=1e-6)
    for value in probabilities.score_matrix.values():
        assert 0.0 <= value <= 1.0

    total_1x2 = (
        probabilities.home_win.value + probabilities.draw.value + probabilities.away_win.value
    )
    assert total_1x2 == pytest.approx(1.0, abs=1e-6)

    assert probabilities.btts_yes.value + probabilities.btts_no.value == pytest.approx(
        1.0, abs=1e-6
    )
    for entry in probabilities.over_under:
        assert entry.over.value + entry.under.value == pytest.approx(1.0, abs=1e-6)
