from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.settled_bet import SettledBet
from src.domain.ports.settled_bet_repository import SettledBetRepository
from src.infrastructure.persistence.mappers import settled_bet_from_model, settled_bet_to_model
from src.infrastructure.persistence.models import SettledBetModel
from src.infrastructure.persistence.upserts import upsert_bookmaker, upsert_match


class SqlAlchemySettledBetRepository(SettledBetRepository):
    """`SettledBetRepository` backed by SQLAlchemy 2.0 async.

    Mirrors `SqlAlchemyValueBetRepository`'s upsert-then-insert shape: the
    nested `Match`/`Bookmaker` are upserted first so the settled bet's
    denormalized row never depends on the caller having saved them
    separately.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, settled_bet: SettledBet) -> None:
        value_bet = settled_bet.value_bet
        await upsert_match(self._session, value_bet.match)
        bookmaker_id = (
            await upsert_bookmaker(self._session, value_bet.bookmaker)
            if value_bet.bookmaker is not None
            else None
        )
        model = settled_bet_to_model(settled_bet, bookmaker_id=bookmaker_id)
        self._session.add(model)
        await self._session.flush()

    async def list_all(self) -> list[SettledBet]:
        stmt = select(SettledBetModel)
        result = await self._session.execute(stmt)
        return [settled_bet_from_model(model) for model in result.scalars().all()]
