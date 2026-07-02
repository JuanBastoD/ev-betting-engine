from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.odds_quote import OddsQuote
from src.domain.ports.odds_repository import OddsRepository
from src.infrastructure.persistence.mappers import odds_quote_from_model, odds_quote_to_model
from src.infrastructure.persistence.models import OddsQuoteModel
from src.infrastructure.persistence.upserts import upsert_bookmaker, upsert_match


class SqlAlchemyOddsRepository(OddsRepository):
    """`OddsRepository` backed by SQLAlchemy 2.0 async.

    `OddsQuote.match` carries the full `Match` entity (since Phase 6), so
    `save` upserts it (and transitively its teams/league) before inserting
    the quote row - same guarantee as `SqlAlchemyValueBetRepository.save`.
    The old `match_id` side-channel kwarg is gone.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, odds_quote: OddsQuote) -> None:
        await upsert_match(self._session, odds_quote.match)
        bookmaker_id = await upsert_bookmaker(self._session, odds_quote.bookmaker)
        model = odds_quote_to_model(odds_quote, bookmaker_id=bookmaker_id)
        self._session.add(model)
        await self._session.flush()

    async def list_by_match_id(self, match_id: str) -> list[OddsQuote]:
        stmt = (
            select(OddsQuoteModel)
            .where(OddsQuoteModel.match_id == match_id)
            .order_by(OddsQuoteModel.quoted_at)
        )
        result = await self._session.execute(stmt)
        return [odds_quote_from_model(model) for model in result.scalars().all()]
