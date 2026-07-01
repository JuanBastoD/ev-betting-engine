from datetime import datetime, timezone

import pytest

from src.domain.entities.league import League
from src.domain.entities.match import Match
from src.domain.entities.player import Player
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_position import PlayerPosition
from src.domain.entities.team import Team


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


def test_valid_player_match_stats_construction(match: Match, player: Player) -> None:
    stats = PlayerMatchStats(
        match=match,
        player=player,
        minutes_played=90,
        started=True,
        shots_total=4,
        shots_on_target=2,
        goals=1,
        assists=0,
        yellow_cards=1,
        red_cards=0,
        corners_won=3,
    )

    assert stats.minutes_played == 90
    assert stats.started is True
    assert stats.corners_won == 3


def test_corners_won_defaults_to_none_when_not_provided(match: Match, player: Player) -> None:
    stats = PlayerMatchStats(
        match=match,
        player=player,
        minutes_played=90,
        started=True,
        shots_total=0,
        shots_on_target=0,
        goals=0,
        assists=0,
        yellow_cards=0,
        red_cards=0,
    )

    assert stats.corners_won is None


@pytest.mark.parametrize(
    "field_name",
    ["minutes_played", "shots_total", "shots_on_target", "goals", "assists", "yellow_cards", "red_cards"],
)
def test_player_match_stats_rejects_negative_counts(field_name: str, match: Match, player: Player) -> None:
    kwargs = {
        "match": match,
        "player": player,
        "minutes_played": 90,
        "started": True,
        "shots_total": 4,
        "shots_on_target": 2,
        "goals": 1,
        "assists": 0,
        "yellow_cards": 0,
        "red_cards": 0,
    }
    kwargs[field_name] = -1

    with pytest.raises(ValueError):
        PlayerMatchStats(**kwargs)


def test_player_match_stats_rejects_negative_corners_won(match: Match, player: Player) -> None:
    with pytest.raises(ValueError):
        PlayerMatchStats(
            match=match,
            player=player,
            minutes_played=90,
            started=True,
            shots_total=4,
            shots_on_target=2,
            goals=1,
            assists=0,
            yellow_cards=0,
            red_cards=0,
            corners_won=-1,
        )


def test_player_match_stats_rejects_shots_on_target_exceeding_shots_total(
    match: Match, player: Player
) -> None:
    with pytest.raises(ValueError):
        PlayerMatchStats(
            match=match,
            player=player,
            minutes_played=90,
            started=True,
            shots_total=1,
            shots_on_target=2,
            goals=0,
            assists=0,
            yellow_cards=0,
            red_cards=0,
        )
