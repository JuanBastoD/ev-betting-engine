"""High-level adapter implementing the domain's PlayerStatsProvider port on
top of the Sportmonks Football API.
"""

from src.domain.entities.injury_status import InjuryStatus
from src.domain.entities.lineup_confirmation import LineupConfirmation
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.ports.player_stats_provider import PlayerStatsProvider
from src.domain.value_objects.probability import Probability
from src.infrastructure.providers.api.player_stats.client import SportmonksClient
from src.infrastructure.providers.api.player_stats.mappers import (
    estimate_start_probability,
    injury_statuses_from_entries,
    lineup_confirmation_from_entry,
    match_from_fixture_ref,
    player_match_stats_from_dto,
)


class SportmonksPlayerStatsProvider(PlayerStatsProvider):
    """`PlayerStatsProvider` backed by Sportmonks.

    `form_window` controls both the default depth of
    `get_player_recent_matches` and how many recent matches are pulled per
    player when estimating start probability for an unconfirmed lineup.
    """

    def __init__(self, client: SportmonksClient, *, form_window: int = 10) -> None:
        self._client = client
        self._form_window = form_window

    async def get_player_recent_matches(self, player_id: str, n: int = 10) -> list[PlayerMatchStats]:
        dtos = await self._client.get_player_recent_matches(player_id, last=n)
        return [player_match_stats_from_dto(dto) for dto in dtos]

    async def get_injury_report(self, match_id: str) -> list[InjuryStatus]:
        entries = await self._client.get_injury_report(match_id)
        return injury_statuses_from_entries(entries)

    async def get_confirmed_lineup(self, match_id: str) -> list[LineupConfirmation]:
        lineup_dto = await self._client.get_fixture_lineup(match_id)
        match = match_from_fixture_ref(lineup_dto.fixture)

        confirmations: list[LineupConfirmation] = []
        for entry in lineup_dto.entries:
            if lineup_dto.is_confirmed:
                start_probability = Probability(1.0 if entry.is_starting else 0.0)
            else:
                # No official lineup yet: fall back to this player's
                # historical start rate. One extra request per unconfirmed
                # player - acceptable for a squad-sized list, but a known
                # N+1 characteristic worth optimizing if Sportmonks exposes
                # a batched "recent matches for many players" endpoint later.
                recent_dtos = await self._client.get_player_recent_matches(
                    entry.player_id, last=self._form_window
                )
                recent_matches = [player_match_stats_from_dto(dto) for dto in recent_dtos]
                start_probability = estimate_start_probability(recent_matches)

            confirmations.append(
                lineup_confirmation_from_entry(
                    entry,
                    match,
                    is_confirmed=lineup_dto.is_confirmed,
                    start_probability=start_probability,
                )
            )
        return confirmations
