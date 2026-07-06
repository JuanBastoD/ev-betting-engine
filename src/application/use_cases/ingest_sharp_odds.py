"""Ingests sharp (Pinnacle) odds and team-form data for one match.

Depends only on domain ports (`SharpOddsProvider`, `StatsProvider`,
`MatchRepository`, `OddsRepository`) - never a concrete provider/repository
implementation. `Match` is registered (upserted) here rather than requiring
a separate "match discovery" step: no port currently exposes "find all
upcoming fixtures for a league" (only provider-specific batch conveniences
do, beyond their ports - a known, already-flagged gap), so callers supply
the `Match` they want tracked and this use case is what makes it persist-able
(`MatchRepository.list_upcoming()` can find it on a later run).

`TeamForm` is deliberately *not* persisted (no `TeamFormRepository` port
exists, matching `InjuryStatus`/`LineupConfirmation`'s "fetched fresh, used
immediately, not archived" pattern) - it's returned for
`DetectMatchValueBetsUseCase` to consume in the same pipeline pass.
"""

from dataclasses import dataclass

from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.team_form import TeamForm
from src.domain.ports.match_repository import MatchRepository
from src.domain.ports.odds_repository import OddsRepository
from src.domain.ports.sharp_odds_provider import SharpOddsProvider
from src.domain.ports.stats_provider import StatsProvider


@dataclass(frozen=True, slots=True)
class SharpOddsIngestionResult:
    match: Match
    sharp_quotes: list[OddsQuote]
    home_form: TeamForm
    away_form: TeamForm


class IngestSharpOddsUseCase:
    def __init__(
        self,
        *,
        sharp_odds_provider: SharpOddsProvider,
        stats_provider: StatsProvider,
        match_repository: MatchRepository,
        odds_repository: OddsRepository,
    ) -> None:
        self._sharp_odds_provider = sharp_odds_provider
        self._stats_provider = stats_provider
        self._match_repository = match_repository
        self._odds_repository = odds_repository

    async def execute(self, match: Match) -> SharpOddsIngestionResult:
        await self._match_repository.save(match)

        sharp_quotes = await self._sharp_odds_provider.get_odds(match)
        for quote in sharp_quotes:
            await self._odds_repository.save(quote)

        home_form = await self._stats_provider.get_team_form(match.home_team)
        away_form = await self._stats_provider.get_team_form(match.away_team)

        return SharpOddsIngestionResult(
            match=match, sharp_quotes=sharp_quotes, home_form=home_form, away_form=away_form
        )
