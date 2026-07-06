"""GET /value-bets - lists persisted value bets, filtered in-memory by
`ListValueBetsUseCase` (see its own docstring for why filtering happens
there rather than via a repository query)."""

from datetime import date

from fastapi import APIRouter, Depends

from src.application.use_cases.list_value_bets import ListValueBetsUseCase, ValueBetFilters
from src.domain.entities.market_type import MarketType
from src.domain.entities.model_source import ModelSource
from src.presentation.api.dependencies import get_list_value_bets_use_case
from src.presentation.api.schemas import ValueBetListResponse, ValueBetSchema

router = APIRouter(tags=["value-bets"])


@router.get("/value-bets", response_model=ValueBetListResponse)
async def list_value_bets(
    league_id: str | None = None,
    min_ev_threshold: float | None = None,
    match_date: date | None = None,
    market_type: MarketType | None = None,
    model_source: ModelSource | None = None,
    use_case: ListValueBetsUseCase = Depends(get_list_value_bets_use_case),
) -> ValueBetListResponse:
    filters = ValueBetFilters(
        league_id=league_id,
        min_ev_threshold=min_ev_threshold,
        match_date=match_date,
        market_type=market_type,
        model_source=model_source,
    )
    value_bets = await use_case.execute(filters)
    return ValueBetListResponse(value_bets=[ValueBetSchema.from_entity(vb) for vb in value_bets])
