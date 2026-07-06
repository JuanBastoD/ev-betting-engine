"""Ingests player-level data for one match: confirmed/estimated lineups,
injury reports, and each involved player's recent match history.

`Player` entities are discovered from the lineup/injury responses
themselves (both `LineupConfirmation`/`InjuryStatus` carry a full `Player`,
Phase 4) rather than needing a separate player-discovery mechanism, and
persisted via `PlayerRepository`. `PlayerMatchStats` are persisted via
`PlayerStatsRepository`. `InjuryStatus`/`LineupConfirmation` themselves are
*not* persisted (no repository port - point-in-time data, same pattern as
`TeamForm`), only returned for `DetectPlayerPropValueBetsUseCase` to use in
the same pipeline pass.
"""

from dataclasses import dataclass, field

from src.domain.entities.injury_status import InjuryStatus
from src.domain.entities.lineup_confirmation import LineupConfirmation
from src.domain.entities.match import Match
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.ports.player_repository import PlayerRepository
from src.domain.ports.player_stats_provider import PlayerStatsProvider
from src.domain.ports.player_stats_repository import PlayerStatsRepository


@dataclass(frozen=True, slots=True)
class PlayerStatsIngestionResult:
    match: Match
    lineup_confirmations: list[LineupConfirmation]
    injury_statuses: list[InjuryStatus]
    recent_stats_by_player_id: dict[str, list[PlayerMatchStats]] = field(default_factory=dict)


class IngestPlayerStatsUseCase:
    def __init__(
        self,
        *,
        player_stats_provider: PlayerStatsProvider,
        player_repository: PlayerRepository,
        player_stats_repository: PlayerStatsRepository,
        recent_matches_window: int = 10,
    ) -> None:
        self._player_stats_provider = player_stats_provider
        self._player_repository = player_repository
        self._player_stats_repository = player_stats_repository
        self._recent_matches_window = recent_matches_window

    async def execute(self, match: Match) -> PlayerStatsIngestionResult:
        lineup_confirmations = await self._player_stats_provider.get_confirmed_lineup(match.id)
        injury_statuses = await self._player_stats_provider.get_injury_report(match.id)

        players_by_id = {c.player.id: c.player for c in lineup_confirmations}
        players_by_id.update({i.player.id: i.player for i in injury_statuses})

        recent_stats_by_player_id: dict[str, list[PlayerMatchStats]] = {}
        for player_id, player in players_by_id.items():
            await self._player_repository.save(player)
            recent_stats = await self._player_stats_provider.get_player_recent_matches(
                player_id, n=self._recent_matches_window
            )
            for stats in recent_stats:
                await self._player_stats_repository.save(stats)
            recent_stats_by_player_id[player_id] = recent_stats

        return PlayerStatsIngestionResult(
            match=match,
            lineup_confirmations=lineup_confirmations,
            injury_statuses=injury_statuses,
            recent_stats_by_player_id=recent_stats_by_player_id,
        )
