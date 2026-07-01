from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.player import Player
from src.domain.entities.player_position import PlayerPosition
from src.domain.entities.team import Team
from src.infrastructure.persistence.repositories.player_repository import SqlAlchemyPlayerRepository


async def test_save_and_get_by_id_round_trip(session: AsyncSession, player: Player) -> None:
    repository = SqlAlchemyPlayerRepository(session)

    await repository.save(player)
    retrieved = await repository.get_by_id(player.id)

    assert retrieved == player


async def test_get_by_id_returns_none_when_missing(session: AsyncSession) -> None:
    repository = SqlAlchemyPlayerRepository(session)

    assert await repository.get_by_id("does-not-exist") is None


async def test_save_upserts_an_existing_player(
    session: AsyncSession, player: Player, home_team: Team
) -> None:
    repository = SqlAlchemyPlayerRepository(session)
    await repository.save(player)

    updated_player = Player(
        id=player.id, name="Updated Name", team=home_team, position=PlayerPosition.MIDFIELDER
    )
    await repository.save(updated_player)

    retrieved = await repository.get_by_id(player.id)

    assert retrieved is not None
    assert retrieved.name == "Updated Name"
    assert retrieved.position is PlayerPosition.MIDFIELDER


async def test_list_by_team_id_returns_only_that_teams_players(
    session: AsyncSession, home_team: Team, away_team: Team
) -> None:
    home_player = Player(id="player-home", name="Home Player", team=home_team, position=PlayerPosition.FORWARD)
    away_player = Player(id="player-away", name="Away Player", team=away_team, position=PlayerPosition.DEFENDER)

    repository = SqlAlchemyPlayerRepository(session)
    await repository.save(home_player)
    await repository.save(away_player)

    home_players = await repository.list_by_team_id(home_team.id)

    assert [p.id for p in home_players] == ["player-home"]


async def test_list_by_team_id_returns_empty_list_when_no_players_exist(
    session: AsyncSession,
) -> None:
    repository = SqlAlchemyPlayerRepository(session)

    assert await repository.list_by_team_id("no-such-team") == []
