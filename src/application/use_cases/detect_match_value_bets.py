"""Runs `MatchValueDetector` for every market quoted on a match.

`MatchValueDetector.detect()` (like `MarketValueDetector.detect()` before
it) prices exactly one market (one `market_type` + `line` combination) per
call - a match typically has several (1X2, Over/Under at multiple lines,
BTTS). Grouping `local_quotes`/`sharp_quotes` by market and calling
`detect()` once per group is pure orchestration (dispatching to the
existing domain service correctly), not new domain logic.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.entities.market_type import MarketType
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.team_form import TeamForm
from src.domain.entities.value_bet import ValueBet
from src.domain.ports.value_bet_repository import ValueBetRepository
from src.domain.services.match_model.match_value_detector import ConfirmationMode, MatchValueDetector
from src.domain.services.match_model.team_strength import calculate_team_strength

_MarketKey = tuple[MarketType, float | None]


@dataclass(frozen=True, slots=True)
class DetectMatchValueBetsUseCase:
    """A plain dataclass rather than a hand-written `__init__` - every
    field is a constructor dependency, no other state."""

    match_value_detector: MatchValueDetector
    value_bet_repository: ValueBetRepository
    league_average_goals: float

    async def execute(
        self,
        *,
        home_form: TeamForm,
        away_form: TeamForm,
        sharp_quotes: Sequence[OddsQuote],
        local_quotes: Sequence[OddsQuote],
    ) -> list[ValueBet]:
        home_strength = calculate_team_strength(
            form=home_form, league_average_goals=self.league_average_goals
        )
        away_strength = calculate_team_strength(
            form=away_form, league_average_goals=self.league_average_goals
        )

        sharp_by_market = _group_by_market(sharp_quotes)
        local_by_market = _group_by_market(local_quotes)

        value_bets: list[ValueBet] = []
        for market_key, local_group in local_by_market.items():
            sharp_group = sharp_by_market.get(market_key)
            if sharp_group is None and self.match_value_detector.mode is ConfirmationMode.CONFIRMATION:
                # Nothing to confirm this market against - skip it rather
                # than letting the detector raise for the whole match.
                continue
            detected = self.match_value_detector.detect(
                home_strength=home_strength,
                away_strength=away_strength,
                league_average_goals=self.league_average_goals,
                local_quotes=local_group,
                sharp_quotes=sharp_group,
            )
            value_bets.extend(detected)

        for value_bet in value_bets:
            await self.value_bet_repository.save(value_bet)

        return value_bets


def _group_by_market(quotes: Sequence[OddsQuote]) -> dict[_MarketKey, list[OddsQuote]]:
    groups: dict[_MarketKey, list[OddsQuote]] = {}
    for quote in quotes:
        key = (quote.selection.market_type, quote.selection.line)
        groups.setdefault(key, []).append(quote)
    return groups
