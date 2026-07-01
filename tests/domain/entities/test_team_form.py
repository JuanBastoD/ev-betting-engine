import pytest

from src.domain.entities.team import Team
from src.domain.entities.team_form import TeamForm


@pytest.fixture
def team() -> Team:
    return Team(id="team-1", name="River Plate")


def test_valid_team_form_construction(team: Team) -> None:
    form = TeamForm(
        team=team,
        matches_played=10,
        wins=6,
        draws=2,
        losses=2,
        goals_for=18,
        goals_against=9,
    )
    assert form.matches_played == 10
    assert form.wins + form.draws + form.losses == form.matches_played


def test_team_form_allows_fewer_than_ten_matches(team: Team) -> None:
    form = TeamForm(
        team=team, matches_played=3, wins=1, draws=1, losses=1, goals_for=4, goals_against=3
    )
    assert form.matches_played == 3


@pytest.mark.parametrize("matches_played", [-1, 11, 20])
def test_team_form_matches_played_must_be_within_window(team: Team, matches_played: int) -> None:
    with pytest.raises(ValueError):
        TeamForm(
            team=team,
            matches_played=matches_played,
            wins=0,
            draws=0,
            losses=0,
            goals_for=0,
            goals_against=0,
        )


def test_team_form_rejects_negative_stat(team: Team) -> None:
    with pytest.raises(ValueError):
        TeamForm(
            team=team, matches_played=5, wins=-1, draws=1, losses=5, goals_for=0, goals_against=0
        )


def test_team_form_requires_wins_draws_losses_to_sum_to_matches_played(team: Team) -> None:
    with pytest.raises(ValueError):
        TeamForm(
            team=team, matches_played=10, wins=6, draws=2, losses=1, goals_for=18, goals_against=9
        )
