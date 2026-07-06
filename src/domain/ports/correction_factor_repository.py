from abc import ABC, abstractmethod

from src.domain.services.calibration.correction_factor import CorrectionFactor


class CorrectionFactorRepository(ABC):
    """Persistence contract for versioned `CorrectionFactor` rows - every
    `save()` call appends a new version, it never updates one in place."""

    @abstractmethod
    async def save(self, correction_factor: CorrectionFactor) -> None: ...

    @abstractmethod
    async def list_all(self) -> list[CorrectionFactor]: ...
