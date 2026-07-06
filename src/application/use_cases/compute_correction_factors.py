"""Runs `CorrectionFactorService` over every settled bet on file and
persists whatever segment-level factors it produces - each call appends a
new, versioned batch (`computed_at`), it never overwrites a previous one.
"""

from dataclasses import dataclass
from datetime import datetime

from src.domain.ports.correction_factor_repository import CorrectionFactorRepository
from src.domain.ports.settled_bet_repository import SettledBetRepository
from src.domain.services.calibration.correction_factor import (
    CorrectionFactor,
    CorrectionFactorService,
)


@dataclass(frozen=True, slots=True)
class ComputeCorrectionFactorsUseCase:
    settled_bet_repository: SettledBetRepository
    correction_factor_repository: CorrectionFactorRepository
    correction_factor_service: CorrectionFactorService

    async def execute(self, *, computed_at: datetime) -> list[CorrectionFactor]:
        settled_bets = await self.settled_bet_repository.list_all()
        factors = self.correction_factor_service.compute_factors(
            settled_bets, computed_at=computed_at
        )
        for factor in factors:
            await self.correction_factor_repository.save(factor)
        return factors
