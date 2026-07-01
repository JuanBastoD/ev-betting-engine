from datetime import datetime, timedelta, timezone

import pytest

from src.domain.entities.league import League
from src.domain.entities.match import Match
from src.domain.entities.team import Team


def test_valid_match_construction(
    home_team: Team, away_team: Team, league: League, kickoff_utc: datetime
) -> None:
    match = Match(
        id="match-1",
        home_team=home_team,
        away_team=away_team,
        league=league,
        kickoff_utc=kickoff_utc,
    )
    assert match.id == "match-1"
    assert match.home_team is home_team
    assert match.away_team is away_team
    assert match.league is league
    assert match.kickoff_utc == kickoff_utc


def test_match_requires_non_empty_id(
    home_team: Team, away_team: Team, league: League, kickoff_utc: datetime
) -> None:
    with pytest.raises(ValueError):
        Match(id="", home_team=home_team, away_team=away_team, league=league, kickoff_utc=kickoff_utc)


def test_match_requires_different_teams(home_team: Team, league: League, kickoff_utc: datetime) -> None:
    with pytest.raises(ValueError):
        Match(
            id="match-1",
            home_team=home_team,
            away_team=home_team,
            league=league,
            kickoff_utc=kickoff_utc,
        )


def test_match_requires_timezone_aware_kickoff(
    home_team: Team, away_team: Team, league: League
) -> None:
    naive_kickoff = datetime(2026, 8, 15, 20, 0)
    with pytest.raises(ValueError):
        Match(
            id="match-1",
            home_team=home_team,
            away_team=away_team,
            league=league,
            kickoff_utc=naive_kickoff,
        )


def test_match_requires_utc_kickoff(home_team: Team, away_team: Team, league: League) -> None:
    non_utc_kickoff = datetime(2026, 8, 15, 20, 0, tzinfo=timezone(timedelta(hours=-3)))
    with pytest.raises(ValueError):
        Match(
            id="match-1",
            home_team=home_team,
            away_team=away_team,
            league=league,
            kickoff_utc=non_utc_kickoff,
        )
