from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.services.calibration.correction_factor import CorrectionFactor
from src.infrastructure.persistence.repositories.correction_factor_repository import (
    SqlAlchemyCorrectionFactorRepository,
)


def _correction_factor(
    segment_value: str = "PLAYER_PROP", computed_at: datetime | None = None
) -> CorrectionFactor:
    return CorrectionFactor(
        segment_type="market_type",
        segment_value=segment_value,
        factor=0.92,
        sample_size=150,
        computed_at=computed_at or datetime(2026, 9, 1, tzinfo=timezone.utc),
        data_range_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        data_range_end=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


async def test_save_and_list_all_round_trip(session: AsyncSession) -> None:
    correction_factor = _correction_factor()
    repository = SqlAlchemyCorrectionFactorRepository(session)

    await repository.save(correction_factor)

    results = await repository.list_all()

    assert results == [correction_factor]


async def test_list_all_returns_empty_list_when_nothing_computed(session: AsyncSession) -> None:
    repository = SqlAlchemyCorrectionFactorRepository(session)
    assert await repository.list_all() == []


async def test_save_never_overwrites_a_previous_version(session: AsyncSession) -> None:
    repository = SqlAlchemyCorrectionFactorRepository(session)
    older = _correction_factor(computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    newer = _correction_factor(computed_at=datetime(2026, 6, 1, tzinfo=timezone.utc))

    await repository.save(older)
    await repository.save(newer)

    results = await repository.list_all()

    assert len(results) == 2
    assert older in results
    assert newer in results
