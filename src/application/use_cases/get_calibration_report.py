"""Fetches every settled bet and hands it to `CalibrationService` for the
`/calibration/report` endpoint. `model_source`/`market_type` are optional
pre-filters applied before segmentation - the same "filter in Python, no
port change" tradeoff `ListValueBetsUseCase` already makes for
`ValueBetRepository`.
"""

from dataclasses import dataclass

from src.domain.entities.market_type import MarketType
from src.domain.entities.model_source import ModelSource
from src.domain.ports.settled_bet_repository import SettledBetRepository
from src.domain.services.calibration.calibration_service import (
    CalibrationReport,
    CalibrationService,
)


@dataclass(frozen=True, slots=True)
class GetCalibrationReportUseCase:
    settled_bet_repository: SettledBetRepository
    calibration_service: CalibrationService

    async def execute(
        self,
        *,
        model_source: ModelSource | None = None,
        market_type: MarketType | None = None,
    ) -> CalibrationReport:
        settled_bets = await self.settled_bet_repository.list_all()
        filtered = [
            settled_bet
            for settled_bet in settled_bets
            if (model_source is None or settled_bet.value_bet.model_source == model_source)
            and (
                market_type is None
                or settled_bet.value_bet.selection.market_type == market_type
            )
        ]
        return self.calibration_service.calculate_segmented(filtered)
