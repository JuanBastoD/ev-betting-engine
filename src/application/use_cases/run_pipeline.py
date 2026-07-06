"""Facade over the five sub-use-cases: runs the full ingest -> detect
pipeline for a set of matches (or one match, for the on-demand query
endpoint - same code path, just a one-element list).

Each step's result feeds directly into the next as a plain Python value -
no repository re-fetch needed between steps, since every ingestion use
case already returns what the next step needs.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from src.application.use_cases.detect_match_value_bets import DetectMatchValueBetsUseCase
from src.application.use_cases.detect_player_prop_value_bets import (
    DetectPlayerPropValueBetsUseCase,
)
from src.application.use_cases.ingest_local_odds import IngestLocalOddsUseCase
from src.application.use_cases.ingest_player_stats import IngestPlayerStatsUseCase
from src.application.use_cases.ingest_sharp_odds import IngestSharpOddsUseCase
from src.domain.entities.match import Match
from src.domain.entities.value_bet import ValueBet
from src.domain.ports.match_repository import MatchRepository


@dataclass(frozen=True, slots=True)
class PipelineRunResult:
    matches_processed: int
    match_value_bets: list[ValueBet]
    player_prop_value_bets: list[ValueBet]


@dataclass(frozen=True, slots=True)
class RunPipelineUseCase:
    match_repository: MatchRepository
    ingest_sharp_odds: IngestSharpOddsUseCase
    ingest_local_odds: IngestLocalOddsUseCase
    ingest_player_stats: IngestPlayerStatsUseCase
    detect_match_value_bets: DetectMatchValueBetsUseCase
    detect_player_prop_value_bets: DetectPlayerPropValueBetsUseCase

    async def execute(self, matches: Sequence[Match] | None = None) -> PipelineRunResult:
        """With no `matches` given, runs over `MatchRepository.list_upcoming()`
        (the scheduled/periodic pipeline run); an explicit list runs the same
        flow for just those matches (the on-demand `/value-bets/query`
        endpoint - a one-element list)."""
        if matches is None:
            matches = await self.match_repository.list_upcoming()

        match_value_bets: list[ValueBet] = []
        player_prop_value_bets: list[ValueBet] = []

        for match in matches:
            sharp_result = await self.ingest_sharp_odds.execute(match)
            local_result = await self.ingest_local_odds.execute(match)
            stats_result = await self.ingest_player_stats.execute(match)

            match_value_bets.extend(
                await self.detect_match_value_bets.execute(
                    home_form=sharp_result.home_form,
                    away_form=sharp_result.away_form,
                    sharp_quotes=sharp_result.sharp_quotes,
                    local_quotes=local_result.local_quotes,
                )
            )

            prop_detections = await self.detect_player_prop_value_bets.execute(
                prop_markets=local_result.prop_markets,
                recent_stats_by_player_id=stats_result.recent_stats_by_player_id,
                lineup_confirmations=stats_result.lineup_confirmations,
                injury_statuses=stats_result.injury_statuses,
            )
            player_prop_value_bets.extend(detection.value_bet for detection in prop_detections)

        return PipelineRunResult(
            matches_processed=len(matches),
            match_value_bets=match_value_bets,
            player_prop_value_bets=player_prop_value_bets,
        )
