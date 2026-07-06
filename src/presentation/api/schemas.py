"""Pydantic request/response models for the API - the only place domain
entities get flattened into plain JSON-friendly shapes. Routers convert;
nothing in `src.application`/`src.domain` knows these types exist.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from src.domain.entities.bet_result import BetResult
from src.domain.entities.market_type import MarketType
from src.domain.entities.model_source import ModelSource
from src.domain.entities.settled_bet import SettledBet
from src.domain.entities.value_bet import ValueBet
from src.domain.services.calibration.calibration_service import (
    CalibrationBucket,
    CalibrationMetrics,
    CalibrationReport,
)
from src.domain.services.calibration.correction_factor import CorrectionFactor


class HealthResponse(BaseModel):
    status: str = "ok"


class ValueBetSchema(BaseModel):
    """Flattened `ValueBet`. `lineup_confirmed` is always present but only
    meaningful (non-null) for `model_source=STATISTICAL` player-prop bets -
    see `ValueBet.lineup_confirmed`'s own docstring."""

    match_id: str
    league_id: str
    market_type: MarketType
    outcome: str
    line: float | None
    local_odds: float
    fair_probability: float
    edge_percentage: float
    suggested_stake_fraction: float
    model_source: ModelSource
    lineup_confirmed: bool | None
    bookmaker: str | None = None

    @classmethod
    def from_entity(cls, value_bet: ValueBet) -> "ValueBetSchema":
        return cls(
            match_id=value_bet.match.id,
            league_id=value_bet.match.league.id,
            market_type=value_bet.selection.market_type,
            outcome=value_bet.selection.outcome,
            line=value_bet.selection.line,
            local_odds=value_bet.local_odds.value,
            fair_probability=value_bet.fair_probability.value,
            edge_percentage=value_bet.edge.value,
            suggested_stake_fraction=value_bet.suggested_stake.amount,
            model_source=value_bet.model_source,
            lineup_confirmed=value_bet.lineup_confirmed,
            bookmaker=value_bet.bookmaker.name if value_bet.bookmaker is not None else None,
        )


class PipelineRunResponse(BaseModel):
    matches_processed: int
    total_value_bets: int
    value_bets_by_market_type: dict[str, int]
    value_bets_by_model_source: dict[str, int]
    value_bets: list[ValueBetSchema]


class ValueBetQueryRequest(BaseModel):
    match_id: str
    player_name: str | None = None
    prop_type: str | None = None


class ValueBetQueryResponse(BaseModel):
    match_id: str
    value_bets: list[ValueBetSchema]


class ValueBetListResponse(BaseModel):
    value_bets: list[ValueBetSchema]


class ValueBetListQuery(BaseModel):
    """Query-string filters for `GET /value-bets`."""

    league_id: str | None = Field(default=None)
    min_ev_threshold: float | None = Field(default=None, ge=0.0)
    match_date: date | None = Field(default=None)
    market_type: MarketType | None = Field(default=None)
    model_source: ModelSource | None = Field(default=None)


class ErrorResponse(BaseModel):
    detail: str


class SettleBetRequest(BaseModel):
    """Body for `POST /value-bets/settle`. `line`/`closing_sharp_odds` are
    optional - `line` is `None` for markets without one (e.g. BTTS/1X2),
    `closing_sharp_odds` is `None` when no closing snapshot was captured."""

    match_id: str
    market_type: MarketType
    outcome: str
    line: float | None = None
    local_odds: float
    result: BetResult
    settled_at: datetime
    closing_sharp_odds: float | None = None


class SettleBetResponse(BaseModel):
    value_bet: ValueBetSchema
    result: BetResult
    settled_at: datetime
    closing_sharp_odds: float | None
    profit_loss: float
    clv: float | None

    @classmethod
    def from_entity(cls, settled_bet: SettledBet) -> "SettleBetResponse":
        return cls(
            value_bet=ValueBetSchema.from_entity(settled_bet.value_bet),
            result=settled_bet.result,
            settled_at=settled_bet.settled_at,
            closing_sharp_odds=(
                settled_bet.closing_sharp_odds.value
                if settled_bet.closing_sharp_odds is not None
                else None
            ),
            profit_loss=settled_bet.profit_loss,
            clv=settled_bet.clv,
        )


class CalibrationBucketSchema(BaseModel):
    lower_bound: float
    upper_bound: float
    predicted_mean: float | None
    observed_frequency: float | None
    sample_size: int

    @classmethod
    def from_entity(cls, bucket: CalibrationBucket) -> "CalibrationBucketSchema":
        return cls(
            lower_bound=bucket.lower_bound,
            upper_bound=bucket.upper_bound,
            predicted_mean=bucket.predicted_mean,
            observed_frequency=bucket.observed_frequency,
            sample_size=bucket.sample_size,
        )


class CalibrationMetricsSchema(BaseModel):
    sample_size: int
    brier_score: float | None
    log_loss: float | None
    average_clv: float | None
    calibration_curve: list[CalibrationBucketSchema]

    @classmethod
    def from_entity(cls, metrics: CalibrationMetrics) -> "CalibrationMetricsSchema":
        return cls(
            sample_size=metrics.sample_size,
            brier_score=metrics.brier_score,
            log_loss=metrics.log_loss,
            average_clv=metrics.average_clv,
            calibration_curve=[
                CalibrationBucketSchema.from_entity(bucket) for bucket in metrics.calibration_curve
            ],
        )


class CalibrationReportResponse(BaseModel):
    overall: CalibrationMetricsSchema
    by_market_type: dict[str, CalibrationMetricsSchema]
    by_bookmaker: dict[str, CalibrationMetricsSchema]
    by_model_source: dict[str, CalibrationMetricsSchema]
    by_prop_type: dict[str, CalibrationMetricsSchema]

    @classmethod
    def from_entity(cls, report: CalibrationReport) -> "CalibrationReportResponse":
        return cls(
            overall=CalibrationMetricsSchema.from_entity(report.overall),
            by_market_type={
                key: CalibrationMetricsSchema.from_entity(value)
                for key, value in report.by_market_type.items()
            },
            by_bookmaker={
                key: CalibrationMetricsSchema.from_entity(value)
                for key, value in report.by_bookmaker.items()
            },
            by_model_source={
                key: CalibrationMetricsSchema.from_entity(value)
                for key, value in report.by_model_source.items()
            },
            by_prop_type={
                key: CalibrationMetricsSchema.from_entity(value)
                for key, value in report.by_prop_type.items()
            },
        )


class CorrectionFactorSchema(BaseModel):
    segment_type: str
    segment_value: str
    factor: float
    sample_size: int
    computed_at: datetime
    data_range_start: datetime
    data_range_end: datetime

    @classmethod
    def from_entity(cls, correction_factor: CorrectionFactor) -> "CorrectionFactorSchema":
        return cls(
            segment_type=correction_factor.segment_type,
            segment_value=correction_factor.segment_value,
            factor=correction_factor.factor,
            sample_size=correction_factor.sample_size,
            computed_at=correction_factor.computed_at,
            data_range_start=correction_factor.data_range_start,
            data_range_end=correction_factor.data_range_end,
        )


class ComputeCorrectionFactorsResponse(BaseModel):
    factors: list[CorrectionFactorSchema]
