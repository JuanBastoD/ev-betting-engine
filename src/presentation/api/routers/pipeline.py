"""POST /pipeline/run and POST /value-bets/query.

Both endpoints run the exact same `RunPipelineUseCase` facade - `run`
drives it over every upcoming match (`MatchRepository.list_upcoming()`),
`query` over a single explicitly-named match, optionally narrowing the
player-prop results afterwards. Neither re-implements the ingest->detect
sequence; they only shape the request/response around it.
"""

import structlog
from fastapi import APIRouter, Depends

from src.application.exceptions import MatchNotFoundError
from src.application.use_cases.run_pipeline import PipelineRunResult, RunPipelineUseCase
from src.domain.entities.value_bet import ValueBet
from src.domain.ports.match_repository import MatchRepository
from src.presentation.api.dependencies import get_match_repository, get_run_pipeline_use_case
from src.presentation.api.schemas import (
    PipelineRunResponse,
    ValueBetQueryRequest,
    ValueBetQueryResponse,
    ValueBetSchema,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["pipeline"])


def _summarize(result: PipelineRunResult) -> PipelineRunResponse:
    all_bets: list[ValueBet] = [*result.match_value_bets, *result.player_prop_value_bets]
    by_market_type: dict[str, int] = {}
    by_model_source: dict[str, int] = {}
    for bet in all_bets:
        market_key = bet.selection.market_type.value
        by_market_type[market_key] = by_market_type.get(market_key, 0) + 1
        source_key = bet.model_source.value
        by_model_source[source_key] = by_model_source.get(source_key, 0) + 1

    return PipelineRunResponse(
        matches_processed=result.matches_processed,
        total_value_bets=len(all_bets),
        value_bets_by_market_type=by_market_type,
        value_bets_by_model_source=by_model_source,
        value_bets=[ValueBetSchema.from_entity(bet) for bet in all_bets],
    )


@router.post("/pipeline/run", response_model=PipelineRunResponse)
async def run_pipeline(
    use_case: RunPipelineUseCase = Depends(get_run_pipeline_use_case),
) -> PipelineRunResponse:
    result = await use_case.execute()
    logger.info(
        "pipeline_run_completed",
        matches_processed=result.matches_processed,
        total_value_bets=len(result.match_value_bets) + len(result.player_prop_value_bets),
    )
    return _summarize(result)


@router.post("/value-bets/query", response_model=ValueBetQueryResponse)
async def query_value_bets(
    request: ValueBetQueryRequest,
    use_case: RunPipelineUseCase = Depends(get_run_pipeline_use_case),
    match_repository: MatchRepository = Depends(get_match_repository),
) -> ValueBetQueryResponse:
    match = await match_repository.get_by_id(request.match_id)
    if match is None:
        raise MatchNotFoundError(request.match_id)

    result = await use_case.execute(matches=[match])
    all_bets: list[ValueBet] = [*result.match_value_bets, *result.player_prop_value_bets]

    if request.player_name is not None:
        needle = request.player_name.casefold()
        all_bets = [bet for bet in all_bets if bet.selection.outcome.casefold().startswith(needle)]
    if request.prop_type is not None:
        all_bets = [bet for bet in all_bets if request.prop_type in bet.selection.outcome]

    logger.info(
        "value_bets_query_completed", match_id=request.match_id, value_bets_found=len(all_bets)
    )
    return ValueBetQueryResponse(
        match_id=request.match_id,
        value_bets=[ValueBetSchema.from_entity(bet) for bet in all_bets],
    )
