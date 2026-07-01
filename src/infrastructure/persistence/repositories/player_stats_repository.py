from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.ports.player_stats_repository import PlayerStatsRepository
from src.infrastructure.persistence.mappers import (
    player_match_stats_from_model,
    player_match_stats_to_model,
)
from src.infrastructure.persistence.models import PlayerMatchStatsModel
from src.infrastructure.persistence.upserts import upsert_match, upsert_player


class SqlAlchemyPlayerStatsRepository(PlayerStatsRepository):
    """`PlayerStatsRepository` backed by SQLAlchemy 2.0 async.

    `PlayerMatchStats` nests full `Match` and `Player` entities, so `save`
    upserts both (and transitively their teams/league) before inserting the
    stats row - the caller doesn't need to have saved either separately.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, stats: PlayerMatchStats) -> None:
        await upsert_match(self._session, stats.match)
        await upsert_player(self._session, stats.player)
        model = player_match_stats_to_model(stats)
        self._session.add(model)
        await self._session.flush()

    async def list_by_player_id(self, player_id: str) -> list[PlayerMatchStats]:
        stmt = select(PlayerMatchStatsModel).where(PlayerMatchStatsModel.player_id == player_id)
        result = await self._session.execute(stmt)
        return [player_match_stats_from_model(model) for model in result.scalars().all()]

    async def list_by_match_id(self, match_id: str) -> list[PlayerMatchStats]:
        stmt = select(PlayerMatchStatsModel).where(PlayerMatchStatsModel.match_id == match_id)
        result = await self._session.execute(stmt)
        return [player_match_stats_from_model(model) for model in result.scalars().all()]
