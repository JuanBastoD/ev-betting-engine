"""Marks a previously-detected `ValueBet` as settled once its real-world
result is known (manual entry today; a future results-API adapter would
call this same use case).

`ValueBet` has no surrogate id to look it up by (see `ValueBetRepository`'s
port), so the match is found by natural key - match id plus the exact
selection (market_type/outcome/line) and local odds it was detected at -
via the existing `list_by_match_id`. Mixing up two same-match bets that
differ only by bookmaker is out of scope: the natural key doesn't include
bookmaker, matching `ValueBetRepository.list_by_match_id`'s own lack of a
bookmaker filter.
"""

from dataclasses import dataclass
from datetime import datetime

from src.application.exceptions import ValueBetNotFoundError
from src.domain.entities.bet_result import BetResult
from src.domain.entities.market_type import MarketType
from src.domain.entities.settled_bet import SettledBet
from src.domain.ports.settled_bet_repository import SettledBetRepository
from src.domain.ports.value_bet_repository import ValueBetRepository
from src.domain.value_objects.decimal_odds import DecimalOdds


@dataclass(frozen=True, slots=True)
class SettleBetUseCase:
    value_bet_repository: ValueBetRepository
    settled_bet_repository: SettledBetRepository

    async def execute(
        self,
        *,
        match_id: str,
        market_type: MarketType,
        outcome: str,
        line: float | None,
        local_odds: float,
        result: BetResult,
        settled_at: datetime,
        closing_sharp_odds: DecimalOdds | None = None,
    ) -> SettledBet:
        value_bets = await self.value_bet_repository.list_by_match_id(match_id)
        value_bet = next(
            (
                vb
                for vb in value_bets
                if vb.selection.market_type == market_type
                and vb.selection.outcome == outcome
                and vb.selection.line == line
                and vb.local_odds.value == local_odds
            ),
            None,
        )
        if value_bet is None:
            raise ValueBetNotFoundError(match_id, outcome)

        settled_bet = SettledBet(
            value_bet=value_bet,
            result=result,
            settled_at=settled_at,
            closing_sharp_odds=closing_sharp_odds,
        )
        await self.settled_bet_repository.save(settled_bet)
        return settled_bet
