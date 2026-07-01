from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.player import Player
from src.domain.ports.player_repository import PlayerRepository
from src.infrastructure.persistence.mappers import player_from_model
from src.infrastructure.persistence.models import PlayerModel
from src.infrastructure.persistence.upserts import upsert_player


class SqlAlchemyPlayerRepository(PlayerRepository):
    """`PlayerRepository` backed by SQLAlchemy 2.0 async.

    Flushes but never commits - the caller owns the transaction boundary.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, player_id: str) -> Player | None:
        model = await self._session.get(PlayerModel, player_id)
        return player_from_model(model) if model is not None else None

    async def list_by_team_id(self, team_id: str) -> list[Player]:
        stmt = select(PlayerModel).where(PlayerModel.team_id == team_id)
        result = await self._session.execute(stmt)
        return [player_from_model(model) for model in result.scalars().all()]

    async def save(self, player: Player) -> None:
        await upsert_player(self._session, player)
