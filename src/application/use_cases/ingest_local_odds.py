"""Ingests local-bookmaker odds - both main match markets and player props -
for one match.

Main-market `OddsQuote`s are persisted via `OddsRepository` (already
tracked historically since Phase 6). `PlayerPropMarket`s are *not*
persisted - there is no repository port for them (deferred since Phase 5,
same "fetched fresh, used immediately" pattern as `TeamForm`/
`InjuryStatus`/`LineupConfirmation`): they are returned for
`DetectPlayerPropValueBetsUseCase` to price in the same pipeline pass.
"""

from dataclasses import dataclass

from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.ports.local_odds_provider import LocalOddsProvider
from src.domain.ports.odds_repository import OddsRepository


@dataclass(frozen=True, slots=True)
class LocalOddsIngestionResult:
    match: Match
    local_quotes: list[OddsQuote]
    prop_markets: list[PlayerPropMarket]


class IngestLocalOddsUseCase:
    def __init__(
        self, *, local_odds_provider: LocalOddsProvider, odds_repository: OddsRepository
    ) -> None:
        self._local_odds_provider = local_odds_provider
        self._odds_repository = odds_repository

    async def execute(self, match: Match) -> LocalOddsIngestionResult:
        local_quotes = await self._local_odds_provider.get_odds(match)
        for quote in local_quotes:
            await self._odds_repository.save(quote)

        prop_markets = await self._local_odds_provider.get_player_props(match)

        return LocalOddsIngestionResult(
            match=match, local_quotes=local_quotes, prop_markets=prop_markets
        )
