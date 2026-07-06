"""team_strength.py tests.

Hand-computed vectors:
  form: 10 matches, goals_for=18, goals_against=9 -> rates 1.8, 0.9
  league_average_goals=1.5 -> attack=1.8/1.5=1.2, defense=0.9/1.5=0.6

  recent_form (5 matches, goals_for=12, goals_against=3 -> rates 2.4, 0.6)
  blended at recent_form_weight=0.6:
    goals_for_rate  = 0.6*2.4 + 0.4*1.8 = 2.16 -> attack = 2.16/1.5 = 1.44
    goals_against_rate = 0.6*0.6 + 0.4*0.9 = 0.72 -> defense = 0.72/1.5 = 0.48
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.domain.entities.team import Team
from src.domain.entities.team_form import TeamForm
from src.domain.services.match_model.team_strength import TeamStrength, calculate_team_strength


@pytest.fixture
def team() -> Team:
    return Team(id="team-1", name="Racing Club")


@pytest.fixture
def form(team: Team) -> TeamForm:
    return TeamForm(
        team=team, matches_played=10, wins=6, draws=2, losses=2, goals_for=18, goals_against=9
    )


@pytest.fixture
def recent_form(team: Team) -> TeamForm:
    return TeamForm(
        team=team, matches_played=5, wins=4, draws=0, losses=1, goals_for=12, goals_against=3
    )


def test_strength_from_a_single_form_matches_the_hand_derived_rates(
    form: TeamForm, team: Team
) -> None:
    strength = calculate_team_strength(form=form, league_average_goals=1.5)

    assert strength.team is team
    assert strength.attack == pytest.approx(1.2)
    assert strength.defense == pytest.approx(0.6)


def test_recent_form_blend_matches_the_hand_derived_weighted_average(
    form: TeamForm, recent_form: TeamForm
) -> None:
    strength = calculate_team_strength(
        form=form, recent_form=recent_form, league_average_goals=1.5, recent_form_weight=0.6
    )

    assert strength.attack == pytest.approx(1.44)
    assert strength.defense == pytest.approx(0.48)


def test_recent_form_weight_of_zero_ignores_recent_form(
    form: TeamForm, recent_form: TeamForm
) -> None:
    blended = calculate_team_strength(
        form=form, recent_form=recent_form, league_average_goals=1.5, recent_form_weight=0.0
    )
    unblended = calculate_team_strength(form=form, league_average_goals=1.5)

    assert blended.attack == pytest.approx(unblended.attack)
    assert blended.defense == pytest.approx(unblended.defense)


def test_recent_form_weight_of_one_uses_only_recent_form(
    form: TeamForm, recent_form: TeamForm
) -> None:
    blended = calculate_team_strength(
        form=form, recent_form=recent_form, league_average_goals=1.5, recent_form_weight=1.0
    )
    recent_only = calculate_team_strength(form=recent_form, league_average_goals=1.5)

    assert blended.attack == pytest.approx(recent_only.attack)
    assert blended.defense == pytest.approx(recent_only.defense)


def test_team_strength_allows_zero_but_not_negative() -> None:
    team = Team(id="t", name="T")
    TeamStrength(team=team, attack=0.0, defense=0.0)  # must not raise

    with pytest.raises(ValueError):
        TeamStrength(team=team, attack=-0.1, defense=1.0)
    with pytest.raises(ValueError):
        TeamStrength(team=team, attack=1.0, defense=-0.1)


def test_league_average_goals_must_be_positive(form: TeamForm) -> None:
    with pytest.raises(ValueError):
        calculate_team_strength(form=form, league_average_goals=0.0)
    with pytest.raises(ValueError):
        calculate_team_strength(form=form, league_average_goals=-1.0)


def test_form_with_zero_matches_played_raises(team: Team) -> None:
    empty_form = TeamForm(
        team=team, matches_played=0, wins=0, draws=0, losses=0, goals_for=0, goals_against=0
    )
    with pytest.raises(ValueError):
        calculate_team_strength(form=empty_form, league_average_goals=1.5)


def test_recent_form_with_zero_matches_played_raises(form: TeamForm, team: Team) -> None:
    empty_recent = TeamForm(
        team=team, matches_played=0, wins=0, draws=0, losses=0, goals_for=0, goals_against=0
    )
    with pytest.raises(ValueError):
        calculate_team_strength(form=form, recent_form=empty_recent, league_average_goals=1.5)


def test_recent_form_for_a_different_team_raises(form: TeamForm) -> None:
    other_team = Team(id="other-team", name="Independiente")
    mismatched_recent = TeamForm(
        team=other_team, matches_played=5, wins=3, draws=1, losses=1, goals_for=8, goals_against=4
    )
    with pytest.raises(ValueError):
        calculate_team_strength(form=form, recent_form=mismatched_recent, league_average_goals=1.5)


@pytest.mark.parametrize("weight", [-0.1, 1.1])
def test_recent_form_weight_out_of_range_raises(
    form: TeamForm, recent_form: TeamForm, weight: float
) -> None:
    with pytest.raises(ValueError):
        calculate_team_strength(
            form=form, recent_form=recent_form, league_average_goals=1.5, recent_form_weight=weight
        )


# --- Property-based tests (hypothesis) ---------------------------------------


@st.composite
def _team_forms(draw: st.DrawFn, team: Team) -> TeamForm:
    matches_played = draw(st.integers(min_value=1, max_value=10))
    wins = draw(st.integers(min_value=0, max_value=matches_played))
    draws = draw(st.integers(min_value=0, max_value=matches_played - wins))
    losses = matches_played - wins - draws
    goals_for = draw(st.integers(min_value=0, max_value=40))
    goals_against = draw(st.integers(min_value=0, max_value=40))
    return TeamForm(
        team=team,
        matches_played=matches_played,
        wins=wins,
        draws=draws,
        losses=losses,
        goals_for=goals_for,
        goals_against=goals_against,
    )


_league_average_goals = st.floats(min_value=0.1, max_value=5.0, allow_nan=False)
_weight = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


@given(data=st.data(), league_average_goals=_league_average_goals, recent_weight=_weight)
def test_property_strength_is_never_negative(
    data: st.DataObject, league_average_goals: float, recent_weight: float
) -> None:
    team = Team(id="t", name="T")
    form = data.draw(_team_forms(team))
    recent_form = data.draw(st.one_of(st.none(), _team_forms(team)))

    strength = calculate_team_strength(
        form=form,
        recent_form=recent_form,
        league_average_goals=league_average_goals,
        recent_form_weight=recent_weight,
    )

    assert strength.attack >= 0.0
    assert strength.defense >= 0.0
