"""Lists persisted `ValueBet`s, filtered in-memory.

`ValueBetRepository`'s port only offers `list_all()`/`list_by_match_id()` -
no server-side filtering by league/EV/date/market/model_source exists on
it, and extending the port for this is out of scope here (it would need a
matching change to every implementation). Filtering the full result set in
Python is the simplest option that needs no port changes; it doesn't scale
to a very large table, a known, explicit tradeoff for this phase.
"""

from dataclasses import dataclass
from datetime import date

from src.domain.entities.market_type import MarketType
from src.domain.entities.model_source import ModelSource
from src.domain.entities.value_bet import ValueBet
from src.domain.ports.value_bet_repository import ValueBetRepository


@dataclass(frozen=True, slots=True)
class ValueBetFilters:
    league_id: str | None = None
    min_ev_threshold: float | None = None
    match_date: date | None = None
    market_type: MarketType | None = None
    model_source: ModelSource | None = None


@dataclass(frozen=True, slots=True)
class ListValueBetsUseCase:
    value_bet_repository: ValueBetRepository

    async def execute(self, filters: ValueBetFilters | None = None) -> list[ValueBet]:
        value_bets = await self.value_bet_repository.list_all()
        if filters is None:
            return value_bets
        return [vb for vb in value_bets if _matches(vb, filters)]


def _matches(value_bet: ValueBet, filters: ValueBetFilters) -> bool:
    if filters.league_id is not None and value_bet.match.league.id != filters.league_id:
        return False
    if filters.min_ev_threshold is not None and value_bet.edge.value < filters.min_ev_threshold * 100.0:
        return False
    if filters.match_date is not None and value_bet.match.kickoff_utc.date() != filters.match_date:
        return False
    if filters.market_type is not None and value_bet.selection.market_type != filters.market_type:
        return False
    if filters.model_source is not None and value_bet.model_source != filters.model_source:
        return False
    return True
