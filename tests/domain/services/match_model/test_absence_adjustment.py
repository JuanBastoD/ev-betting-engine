"""absence_adjustment.py tests.

Hand-computed vectors (default reduction_per_key_absence=0.15,
doubtful_weight=0.5, min_goal_involvements=3):
  one confirmed key absence:   adjusted = attack * 0.85
  two confirmed key absences:  adjusted = attack * 0.85**2 = attack * 0.7225
  one doubtful key absence:    adjusted = attack * (1 - 0.15*0.5) = attack * 0.925
"""

from datetime import datetime, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.domain.entities.injury_status import InjuryStatus
from src.domain.entities.injury_status_type import InjuryStatusType
from src.domain.entities.match import Match
from src.domain.entities.player import Player
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_position import PlayerPosition
from src.domain.entities.team import Team
from src.domain.services.match_model.absence_adjustment import apply_absence_adjustment

UPDATED_AT = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def team() -> Team:
    return Team(id="team-1", name="River Plate")


@pytest.fixture
def striker(team: Team) -> Player:
    return Player(id="p-striker", name="Striker", team=team, position=PlayerPosition.FORWARD)


@pytest.fixture
def playmaker(team: Team) -> Player:
    return Player(id="p-playmaker", name="Playmaker", team=team, position=PlayerPosition.MIDFIELDER)


@pytest.fixture
def defender(team: Team) -> Player:
    return Player(id="p-defender", name="Defender", team=team, position=PlayerPosition.DEFENDER)


@pytest.fixture
def match(team: Team) -> Match:
    away = Team(id="team-2", name="Boca Juniors")
    from src.domain.entities.league import League

    return Match(
        id="match-1",
        home_team=team,
        away_team=away,
        league=League(id="l", name="Liga"),
        kickoff_utc=UPDATED_AT,
    )


def _injury(player: Player, status: InjuryStatusType) -> InjuryStatus:
    return InjuryStatus(player=player, status=status, source="test", updated_at=UPDATED_AT)


def _stats(match: Match, player: Player, *, goals: int, assists: int) -> PlayerMatchStats:
    return PlayerMatchStats(
        match=match,
        player=player,
        minutes_played=90,
        started=True,
        shots_total=goals + 2,
        shots_on_target=goals,
        goals=goals,
        assists=assists,
        yellow_cards=0,
        red_cards=0,
    )


def test_confirmed_key_absence_applies_the_full_reduction(
    match: Match, striker: Player
) -> None:
    result = apply_absence_adjustment(
        1.2,
        injury_statuses=[_injury(striker, InjuryStatusType.INJURED)],
        squad_recent_stats=[_stats(match, striker, goals=4, assists=1)],
    )

    assert result.adjusted_attack == pytest.approx(1.2 * 0.85)
    assert result.has_unconfirmed_absences is False


def test_suspended_is_treated_as_confirmed(match: Match, striker: Player) -> None:
    result = apply_absence_adjustment(
        1.2,
        injury_statuses=[_injury(striker, InjuryStatusType.SUSPENDED)],
        squad_recent_stats=[_stats(match, striker, goals=4, assists=1)],
    )

    assert result.adjusted_attack == pytest.approx(1.2 * 0.85)
    assert result.has_unconfirmed_absences is False


def test_two_confirmed_key_absences_compound_multiplicatively(
    match: Match, striker: Player, playmaker: Player
) -> None:
    result = apply_absence_adjustment(
        1.2,
        injury_statuses=[
            _injury(striker, InjuryStatusType.INJURED),
            _injury(playmaker, InjuryStatusType.SUSPENDED),
        ],
        squad_recent_stats=[
            _stats(match, striker, goals=4, assists=1),
            _stats(match, playmaker, goals=1, assists=3),
        ],
    )

    assert result.adjusted_attack == pytest.approx(1.2 * 0.85 * 0.85)


def test_doubtful_key_absence_applies_a_discounted_reduction_and_flags_uncertainty(
    match: Match, striker: Player
) -> None:
    result = apply_absence_adjustment(
        1.2,
        injury_statuses=[_injury(striker, InjuryStatusType.DOUBTFUL)],
        squad_recent_stats=[_stats(match, striker, goals=4, assists=1)],
    )

    assert result.adjusted_attack == pytest.approx(1.2 * (1 - 0.15 * 0.5))
    assert result.has_unconfirmed_absences is True


def test_fit_status_is_not_an_absence(match: Match, striker: Player) -> None:
    result = apply_absence_adjustment(
        1.2,
        injury_statuses=[_injury(striker, InjuryStatusType.FIT)],
        squad_recent_stats=[_stats(match, striker, goals=4, assists=1)],
    )

    assert result.adjusted_attack == pytest.approx(1.2)
    assert result.has_unconfirmed_absences is False


def test_non_key_position_is_not_reduced(match: Match, defender: Player) -> None:
    result = apply_absence_adjustment(
        1.2,
        injury_statuses=[_injury(defender, InjuryStatusType.INJURED)],
        squad_recent_stats=[_stats(match, defender, goals=4, assists=1)],
    )

    assert result.adjusted_attack == pytest.approx(1.2)


def test_low_goal_involvement_is_not_reduced(match: Match, striker: Player) -> None:
    result = apply_absence_adjustment(
        1.2,
        injury_statuses=[_injury(striker, InjuryStatusType.INJURED)],
        squad_recent_stats=[_stats(match, striker, goals=1, assists=1)],  # 2 < default 3
    )

    assert result.adjusted_attack == pytest.approx(1.2)


def test_no_matching_stats_means_zero_involvement_and_no_reduction(
    match: Match, striker: Player
) -> None:
    result = apply_absence_adjustment(
        1.2, injury_statuses=[_injury(striker, InjuryStatusType.INJURED)], squad_recent_stats=[]
    )

    assert result.adjusted_attack == pytest.approx(1.2)


def test_min_goal_involvements_is_configurable(match: Match, striker: Player) -> None:
    result = apply_absence_adjustment(
        1.2,
        injury_statuses=[_injury(striker, InjuryStatusType.INJURED)],
        squad_recent_stats=[_stats(match, striker, goals=1, assists=1)],
        min_goal_involvements=2,
    )

    assert result.adjusted_attack == pytest.approx(1.2 * 0.85)


def test_reduction_per_key_absence_is_configurable(match: Match, striker: Player) -> None:
    result = apply_absence_adjustment(
        1.2,
        injury_statuses=[_injury(striker, InjuryStatusType.INJURED)],
        squad_recent_stats=[_stats(match, striker, goals=4, assists=1)],
        reduction_per_key_absence=0.30,
    )

    assert result.adjusted_attack == pytest.approx(1.2 * 0.70)


def test_key_positions_is_configurable(match: Match, defender: Player) -> None:
    result = apply_absence_adjustment(
        1.2,
        injury_statuses=[_injury(defender, InjuryStatusType.INJURED)],
        squad_recent_stats=[_stats(match, defender, goals=4, assists=1)],
        key_positions=frozenset({PlayerPosition.DEFENDER}),
    )

    assert result.adjusted_attack == pytest.approx(1.2 * 0.85)


@pytest.mark.parametrize("attack_strength", [-0.1, -1.0])
def test_negative_attack_strength_raises(attack_strength: float) -> None:
    with pytest.raises(ValueError):
        apply_absence_adjustment(attack_strength, injury_statuses=[], squad_recent_stats=[])


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_reduction_per_key_absence_out_of_range_raises(value: float) -> None:
    with pytest.raises(ValueError):
        apply_absence_adjustment(
            1.0, injury_statuses=[], squad_recent_stats=[], reduction_per_key_absence=value
        )


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_doubtful_weight_out_of_range_raises(value: float) -> None:
    with pytest.raises(ValueError):
        apply_absence_adjustment(1.0, injury_statuses=[], squad_recent_stats=[], doubtful_weight=value)


# --- Property-based tests (hypothesis) ---------------------------------------

_attack = st.floats(min_value=0.0, max_value=5.0, allow_nan=False)
_involvements = st.integers(min_value=0, max_value=10)
_status = st.sampled_from(list(InjuryStatusType))
_position = st.sampled_from(list(PlayerPosition))


def _module_match() -> Match:
    from src.domain.entities.league import League

    home = Team(id="team-1", name="River Plate")
    away = Team(id="team-2", name="Boca Juniors")
    return Match(
        id="match-1", home_team=home, away_team=away, league=League(id="l", name="Liga"),
        kickoff_utc=UPDATED_AT,
    )


# Hypothesis flags function-scoped pytest fixtures under @given (not reset
# between generated examples) - these entities are immutable/side-effect-free,
# so building them once as plain module constants sidesteps that safely.
_MATCH = _module_match()
_STRIKER = Player(id="p-striker", name="Striker", team=_MATCH.home_team, position=PlayerPosition.FORWARD)


@given(
    attack_strength=_attack,
    status=_status,
    position=_position,
    involvements=_involvements,
)
def test_property_adjustment_never_increases_attack_and_stays_non_negative(
    attack_strength: float, status: InjuryStatusType, position: PlayerPosition, involvements: int
) -> None:
    player = Player(id="p", name="P", team=_MATCH.home_team, position=position)
    result = apply_absence_adjustment(
        attack_strength,
        injury_statuses=[_injury(player, status)],
        squad_recent_stats=[_stats(_MATCH, player, goals=involvements, assists=0)],
    )

    assert 0.0 <= result.adjusted_attack <= attack_strength


@given(attack_strength=_attack, involvements=_involvements)
def test_property_unconfirmed_flag_is_true_iff_a_significant_doubtful_absence_exists(
    attack_strength: float, involvements: int
) -> None:
    result = apply_absence_adjustment(
        attack_strength,
        injury_statuses=[_injury(_STRIKER, InjuryStatusType.DOUBTFUL)],
        squad_recent_stats=[_stats(_MATCH, _STRIKER, goals=involvements, assists=0)],
    )

    assert result.has_unconfirmed_absences == (involvements >= 3)
