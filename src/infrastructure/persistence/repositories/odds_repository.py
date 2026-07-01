from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.odds_quote import OddsQuote
from src.domain.ports.odds_repository import OddsRepository
from src.infrastructure.persistence.mappers import odds_quote_from_model, odds_quote_to_model
from src.infrastructure.persistence.models import OddsQuoteModel
from src.infrastructure.persistence.upserts import upsert_bookmaker


class SqlAlchemyOddsRepository(OddsRepository):
    """`OddsRepository` backed by SQLAlchemy 2.0 async.

    Known deviation from the port: the domain `OddsQuote` entity carries no
    match reference (only bookmaker/selection/odds/timestamp), yet
    `list_by_match_id` requires one. `save` therefore accepts an optional
    `match_id` beyond `OddsRepository.save(odds_quote)` to make that query
    possible - a caller that only knows the abstract port type can still
    call `save(odds_quote)` validly; the quote is then persisted without a
    match association. Fixing this properly means adding a match reference
    to `OddsQuote`/`Selection` in the domain, which this phase does not
    touch.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, odds_quote: OddsQuote, match_id: str | None = None) -> None:
        bookmaker_id = await upsert_bookmaker(self._session, odds_quote.bookmaker)
        model = odds_quote_to_model(odds_quote, bookmaker_id=bookmaker_id, match_id=match_id)
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
