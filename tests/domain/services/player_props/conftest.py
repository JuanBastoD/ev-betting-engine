from collections.abc import Callable
from datetime import datetime, timezone

import pytest

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.league import League
from src.domain.entities.match import Match
from src.domain.entities.player import Player
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_position import PlayerPosition
from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.entities.player_prop_type import PlayerPropType
from src.domain.entities.team import Team
from src.domain.value_objects.decimal_odds import DecimalOdds

QUOTED_AT = datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc)


@pytest.fixture
def home_team() -> Team:
    return Team(id="team-home", name="River Plate", country="Argentina")


@pytest.fixture
def away_team() -> Team:
    return Team(id="team-away", name="Boca Juniors", country="Argentina")


@pytest.fixture
def league() -> League:
    return League(id="league-1", name="Liga Profesional", country="Argentina")


@pytest.fixture
def match(home_team: Team, away_team: Team, league: League) -> Match:
    return Match(
        id="match-1", home_team=home_team, away_team=away_team, league=league, kickoff_utc=KICKOFF
    )


@pytest.fixture
def player(home_team: Team) -> Player:
    return Player(id="player-1", name="Carlos Bacca", team=home_team, position=PlayerPosition.FORWARD)


@pytest.fixture
def local_bookmaker() -> Bookmaker:
    return Bookmaker(name="Betplay", is_sharp=False, region="CO")


@pytest.fixture
def make_stats(match: Match, player: Player) -> Callable[..., PlayerMatchStats]:
    def _make(
        *,
        minutes_played: int = 90,
        shots_on_target: int = 0,
        goals: int = 0,
        assists: int = 0,
        yellow_cards: int = 0,
        red_cards: int = 0,
    ) -> PlayerMatchStats:
        return PlayerMatchStats(
            match=match,
            player=player,
            minutes_played=minutes_played,
            started=minutes_played > 0,
            shots_total=shots_on_target + 2,
            shots_on_target=shots_on_target,
            goals=goals,
            assists=assists,
            yellow_cards=yellow_cards,
            red_cards=red_cards,
        )

    return _make


@pytest.fixture
def make_prop_market(
    match: Match, local_bookmaker: Bookmaker, player: Player
) -> Callable[..., PlayerPropMarket]:
    def _make(
        *,
        prop_type: PlayerPropType = PlayerPropType.SHOTS_ON_TARGET,
        outcome: str = "Over",
        line: float | None = 1.5,
        odds_value: float = 1.90,
        player_name: str | None = None,
    ) -> PlayerPropMarket:
        return PlayerPropMarket(
            match=match,
            bookmaker=local_bookmaker,
            player_name=player_name or player.name,
            prop_type=prop_type,
            outcome=outcome,
            line=line,
            odds=DecimalOdds(odds_value),
            quoted_at=QUOTED_AT,
        )

    return _make
