from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.ports.correction_factor_repository import CorrectionFactorRepository
from src.domain.services.calibration.correction_factor import CorrectionFactor
from src.infrastructure.persistence.mappers import (
    correction_factor_from_model,
    correction_factor_to_model,
)
from src.infrastructure.persistence.models import CalibrationFactorModel


class SqlAlchemyCorrectionFactorRepository(CorrectionFactorRepository):
    """`CorrectionFactorRepository` backed by SQLAlchemy 2.0 async.

    `save` always inserts a new row - `CorrectionFactor` is versioned by
    design (Phase 10), never updated in place.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, correction_factor: CorrectionFactor) -> None:
        model = correction_factor_to_model(correction_factor)
        self._session.add(model)
        await self._session.flush()

    async def list_all(self) -> list[CorrectionFactor]:
        stmt = select(CalibrationFactorModel)
        result = await self._session.execute(stmt)
        return [correction_factor_from_model(model) for model in result.scalars().all()]
