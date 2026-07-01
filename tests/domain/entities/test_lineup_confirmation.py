from datetime import datetime, timezone

import pytest

from src.domain.entities.league import League
from src.domain.entities.lineup_confirmation import LineupConfirmation
from src.domain.entities.match import Match
from src.domain.entities.player import Player
from src.domain.entities.player_position import PlayerPosition
from src.domain.entities.team import Team
from src.domain.value_objects.probability import Probability


@pytest.fixture
def match() -> Match:
    return Match(
        id="match-1",
        home_team=Team(id="team-home", name="River Plate"),
        away_team=Team(id="team-away", name="Boca Juniors"),
        league=League(id="league-1", name="Liga Profesional"),
        kickoff_utc=datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def player() -> Player:
    return Player(
        id="player-1",
        name="Julian Alvarez",
        team=Team(id="team-home", name="River Plate"),
        position=PlayerPosition.FORWARD,
    )


def test_valid_confirmed_starting_lineup(match: Match, player: Player) -> None:
    confirmation = LineupConfirmation(
        player=player,
        match=match,
        is_starting=True,
        is_confirmed=True,
        start_probability=Probability(1.0),
    )

    assert confirmation.is_starting is True
    assert confirmation.is_confirmed is True
    assert confirmation.start_probability.value == 1.0


def test_valid_confirmed_non_starting_lineup(match: Match, player: Player) -> None:
    confirmation = LineupConfirmation(
        player=player,
        match=match,
        is_starting=False,
        is_confirmed=True,
        start_probability=Probability(0.0),
    )

    assert confirmation.is_starting is False


def test_valid_unconfirmed_estimated_lineup(match: Match, player: Player) -> None:
    confirmation = LineupConfirmation(
        player=player,
        match=match,
        is_starting=True,
        is_confirmed=False,
        start_probability=Probability(0.7),
    )

    assert confirmation.is_confirmed is False
    assert confirmation.start_probability.value == 0.7


@pytest.mark.parametrize(
    ("is_starting", "probability_value"),
    [(True, 0.4), (False, 0.6), (True, 0.0), (False, 1.0)],
)
def test_is_starting_must_match_start_probability_threshold(
    match: Match, player: Player, is_starting: bool, probability_value: float
) -> None:
    with pytest.raises(ValueError):
        LineupConfirmation(
            player=player,
            match=match,
            is_starting=is_starting,
            is_confirmed=False,
            start_probability=Probability(probability_value),
        )


@pytest.mark.parametrize("probability_value", [0.5, 0.7, 0.99])
def test_confirmed_lineup_requires_a_zero_or_one_probability(
    match: Match, player: Player, probability_value: float
) -> None:
    with pytest.raises(ValueError):
        LineupConfirmation(
            player=player,
            match=match,
            is_starting=True,
            is_confirmed=True,
            start_probability=Probability(probability_value),
        )
