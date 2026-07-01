from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.league import League
from src.domain.entities.match import Match
from src.domain.entities.player import Player
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_position import PlayerPosition
from src.domain.entities.team import Team
from src.infrastructure.persistence.repositories.player_repository import SqlAlchemyPlayerRepository
from src.infrastructure.persistence.repositories.player_stats_repository import (
    SqlAlchemyPlayerStatsRepository,
)


def _stats(match: Match, player: Player, *, minutes_played: int = 90) -> PlayerMatchStats:
    return PlayerMatchStats(
        match=match,
        player=player,
        minutes_played=minutes_played,
        started=True,
        shots_total=4,
        shots_on_target=2,
        goals=1,
        assists=0,
        yellow_cards=0,
        red_cards=0,
        corners_won=2,
    )


async def test_save_and_list_by_match_id_round_trip(
    session: AsyncSession, match: Match, player: Player
) -> None:
    stats = _stats(match, player)
    repository = SqlAlchemyPlayerStatsRepository(session)

    await repository.save(stats)

    results = await repository.list_by_match_id(match.id)

    assert results == [stats]


async def test_save_and_list_by_player_id_round_trip(
    session: AsyncSession, match: Match, player: Player
) -> None:
    stats = _stats(match, player)
    repository = SqlAlchemyPlayerStatsRepository(session)

    await repository.save(stats)

    results = await repository.list_by_player_id(player.id)

    assert results == [stats]


async def test_save_upserts_match_and_player_without_prior_saves(
    session: AsyncSession, match: Match, player: Player
) -> None:
    stats = _stats(match, player)
    await SqlAlchemyPlayerStatsRepository(session).save(stats)

    persisted_player = await SqlAlchemyPlayerRepository(session).get_by_id(player.id)

    assert persisted_player == player


async def test_list_by_player_id_returns_stats_across_multiple_matches(
    session: AsyncSession, home_team: Team, away_team: Team, league: League, player: Player
) -> None:
    match_a = Match(
        id="match-a",
        home_team=home_team,
        away_team=away_team,
        league=league,
        kickoff_utc=datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc),
    )
    match_b = Match(
        id="match-b",
        home_team=home_team,
        away_team=away_team,
        league=league,
        kickoff_utc=datetime(2026, 8, 22, 20, 0, tzinfo=timezone.utc),
    )

    repository = SqlAlchemyPlayerStatsRepository(session)
    await repository.save(_stats(match_a, player, minutes_played=90))
    await repository.save(_stats(match_b, player, minutes_played=45))

    results = await repository.list_by_player_id(player.id)

    assert {stats.match.id for stats in results} == {"match-a", "match-b"}


async def test_list_by_match_id_returns_empty_list_when_no_stats_exist(
    session: AsyncSession,
) -> None:
    repository = SqlAlchemyPlayerStatsRepository(session)

    assert await repository.list_by_match_id("no-such-match") == []


async def test_list_by_player_id_returns_empty_list_when_no_stats_exist(
    session: AsyncSession,
) -> None:
    repository = SqlAlchemyPlayerStatsRepository(session)

    assert await repository.list_by_player_id("no-such-player") == []
