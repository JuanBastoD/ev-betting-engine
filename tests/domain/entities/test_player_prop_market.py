from datetime import datetime, timedelta, timezone

import pytest

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.league import League
from src.domain.entities.match import Match
from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.entities.player_prop_type import PlayerPropType
from src.domain.entities.team import Team
from src.domain.value_objects.decimal_odds import DecimalOdds


@pytest.fixture
def match(home_team: Team, away_team: Team, league: League, kickoff_utc: datetime) -> Match:
    return Match(
        id="match-1",
        home_team=home_team,
        away_team=away_team,
        league=league,
        kickoff_utc=kickoff_utc,
    )


@pytest.fixture
def bookmaker() -> Bookmaker:
    return Bookmaker(name="Betplay", is_sharp=False, region="CO")


@pytest.fixture
def quoted_at() -> datetime:
    return datetime(2026, 8, 15, 19, 0, tzinfo=timezone.utc)


def _prop(match: Match, bookmaker: Bookmaker, quoted_at: datetime, **overrides: object) -> PlayerPropMarket:
    kwargs: dict = dict(
        match=match,
        bookmaker=bookmaker,
        player_name="Carlos Bacca",
        prop_type=PlayerPropType.SHOTS_ON_TARGET,
        outcome="Over",
        line=1.5,
        odds=DecimalOdds(1.85),
        quoted_at=quoted_at,
    )
    kwargs.update(overrides)
    return PlayerPropMarket(**kwargs)


def test_valid_player_prop_market_construction(
    match: Match, bookmaker: Bookmaker, quoted_at: datetime
) -> None:
    prop = _prop(match, bookmaker, quoted_at)
    assert prop.match is match
    assert prop.bookmaker is bookmaker
    assert prop.player_name == "Carlos Bacca"
    assert prop.prop_type is PlayerPropType.SHOTS_ON_TARGET
    assert prop.outcome == "Over"
    assert prop.line == 1.5
    assert prop.odds.value == 1.85
    assert prop.quoted_at == quoted_at


def test_line_may_be_none_for_lineless_props(
    match: Match, bookmaker: Bookmaker, quoted_at: datetime
) -> None:
    prop = _prop(
        match, bookmaker, quoted_at, prop_type=PlayerPropType.GOALS, outcome="Yes", line=None
    )
    assert prop.line is None


def test_player_prop_market_requires_player_name(
    match: Match, bookmaker: Bookmaker, quoted_at: datetime
) -> None:
    with pytest.raises(ValueError):
        _prop(match, bookmaker, quoted_at, player_name="")


def test_player_prop_market_requires_outcome(
    match: Match, bookmaker: Bookmaker, quoted_at: datetime
) -> None:
    with pytest.raises(ValueError):
        _prop(match, bookmaker, quoted_at, outcome="")


def test_player_prop_market_rejects_non_positive_line(
    match: Match, bookmaker: Bookmaker, quoted_at: datetime
) -> None:
    with pytest.raises(ValueError):
        _prop(match, bookmaker, quoted_at, line=0.0)


def test_player_prop_market_requires_timezone_aware_timestamp(
    match: Match, bookmaker: Bookmaker
) -> None:
    with pytest.raises(ValueError):
        _prop(match, bookmaker, datetime(2026, 8, 15, 19, 0))


def test_player_prop_market_requires_utc_timestamp(match: Match, bookmaker: Bookmaker) -> None:
    with pytest.raises(ValueError):
        _prop(match, bookmaker, datetime(2026, 8, 15, 19, 0, tzinfo=timezone(timedelta(hours=-5))))
