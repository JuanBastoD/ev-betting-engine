"""GET /calibration/report (Level 1 backtesting dashboard data), plus two
supplementary endpoints needed to feed it: POST /value-bets/settle (record
a real-world result) and POST /calibration/factors/recompute (persist a new
versioned batch of CorrectionFactors from whatever's been settled so far).
"""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends

from src.application.use_cases.compute_correction_factors import (
    ComputeCorrectionFactorsUseCase,
)
from src.application.use_cases.get_calibration_report import GetCalibrationReportUseCase
from src.application.use_cases.settle_bet import SettleBetUseCase
from src.domain.entities.market_type import MarketType
from src.domain.entities.model_source import ModelSource
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.presentation.api.dependencies import (
    get_calibration_report_use_case,
    get_compute_correction_factors_use_case,
    get_settle_bet_use_case,
)
from src.presentation.api.schemas import (
    CalibrationReportResponse,
    ComputeCorrectionFactorsResponse,
    CorrectionFactorSchema,
    SettleBetRequest,
    SettleBetResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["calibration"])


@router.post("/value-bets/settle", response_model=SettleBetResponse)
async def settle_bet(
    request: SettleBetRequest,
    use_case: SettleBetUseCase = Depends(get_settle_bet_use_case),
) -> SettleBetResponse:
    settled_bet = await use_case.execute(
        match_id=request.match_id,
        market_type=request.market_type,
        outcome=request.outcome,
        line=request.line,
        local_odds=request.local_odds,
        result=request.result,
        settled_at=request.settled_at,
        closing_sharp_odds=(
            DecimalOdds(request.closing_sharp_odds)
            if request.closing_sharp_odds is not None
            else None
        ),
    )
    logger.info(
        "bet_settled",
        match_id=request.match_id,
        outcome=request.outcome,
        result=request.result.value,
    )
    return SettleBetResponse.from_entity(settled_bet)


@router.get("/calibration/report", response_model=CalibrationReportResponse)
async def get_calibration_report(
    model_source: ModelSource | None = None,
    market_type: MarketType | None = None,
    use_case: GetCalibrationReportUseCase = Depends(get_calibration_report_use_case),
) -> CalibrationReportResponse:
    report = await use_case.execute(model_source=model_source, market_type=market_type)
    return CalibrationReportResponse.from_entity(report)


@router.post("/calibration/factors/recompute", response_model=ComputeCorrectionFactorsResponse)
async def recompute_correction_factors(
    use_case: ComputeCorrectionFactorsUseCase = Depends(get_compute_correction_factors_use_case),
) -> ComputeCorrectionFactorsResponse:
    factors = await use_case.execute(computed_at=datetime.now(UTC))
    logger.info("correction_factors_recomputed", factor_count=len(factors))
    return ComputeCorrectionFactorsResponse(
        factors=[CorrectionFactorSchema.from_entity(factor) for factor in factors]
    )
