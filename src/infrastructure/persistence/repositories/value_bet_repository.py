from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.value_bet import ValueBet
from src.domain.ports.value_bet_repository import ValueBetRepository
from src.infrastructure.persistence.mappers import value_bet_from_model, value_bet_to_model
from src.infrastructure.persistence.models import ValueBetModel
from src.infrastructure.persistence.upserts import upsert_bookmaker, upsert_match


class SqlAlchemyValueBetRepository(ValueBetRepository):
    """`ValueBetRepository` backed by SQLAlchemy 2.0 async.

    `ValueBet.match` carries the full `Match` entity, so `save` upserts it
    (and transitively its teams/league) before inserting the value bet row,
    guaranteeing the `matches.id` foreign key is satisfied without requiring
    the caller to have saved the match separately first. `ValueBet.bookmaker`
    (Phase 10) is optional, so it's only upserted when present.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, value_bet: ValueBet) -> None:
        await upsert_match(self._session, value_bet.match)
        bookmaker_id = (
            await upsert_bookmaker(self._session, value_bet.bookmaker)
            if value_bet.bookmaker is not None
            else None
        )
        model = value_bet_to_model(value_bet, bookmaker_id=bookmaker_id)
        self._session.add(model)
        await self._session.flush()

    async def list_by_match_id(self, match_id: str) -> list[ValueBet]:
        stmt = select(ValueBetModel).where(ValueBetModel.match_id == match_id)
        result = await self._session.execute(stmt)
        return [value_bet_from_model(model) for model in result.scalars().all()]

    async def list_all(self) -> list[ValueBet]:
        stmt = select(ValueBetModel)
        result = await self._session.execute(stmt)
        return [value_bet_from_model(model) for model in result.scalars().all()]
