from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.match import Match
from src.domain.ports.match_repository import MatchRepository
from src.infrastructure.persistence.mappers import match_from_model
from src.infrastructure.persistence.models import MatchModel
from src.infrastructure.persistence.upserts import upsert_match


class SqlAlchemyMatchRepository(MatchRepository):
    """`MatchRepository` backed by SQLAlchemy 2.0 async.

    Receives its `AsyncSession` by dependency injection - the caller (a
    future use case) owns the transaction boundary: this repository only
    `flush`es, it never `commit`s or `rollback`s.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, match_id: str) -> Match | None:
        model = await self._session.get(MatchModel, match_id)
        return match_from_model(model) if model is not None else None

    async def list_upcoming(self) -> list[Match]:
        now = datetime.now(timezone.utc)
        stmt = (
            select(MatchModel)
            .where(MatchModel.kickoff_utc >= now)
            .order_by(MatchModel.kickoff_utc)
        )
        result = await self._session.execute(stmt)
        return [match_from_model(model) for model in result.scalars().all()]

    async def save(self, match: Match) -> None:
        await upsert_match(self._session, match)
