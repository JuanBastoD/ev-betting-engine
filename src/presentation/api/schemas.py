"""Pydantic request/response models for the API - the only place domain
entities get flattened into plain JSON-friendly shapes. Routers convert;
nothing in `src.application`/`src.domain` knows these types exist.
"""

from datetime import date

from pydantic import BaseModel, Field

from src.domain.entities.market_type import MarketType
from src.domain.entities.model_source import ModelSource
from src.domain.entities.value_bet import ValueBet


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
