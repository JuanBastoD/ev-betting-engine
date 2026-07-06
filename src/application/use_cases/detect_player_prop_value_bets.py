"""Runs `PlayerPropDetector` for every `PlayerPropMarket` quoted for a match.

Resolves each market's bookmaker-supplied `player_name` (a display label,
not a `Player` reference - `PlayerPropMarket`'s own docstring flags this as
an application-layer matching concern) against the players we actually
have lineup/injury data for, by exact case-insensitive name match. A prop
for a player we have no data on can't be priced and is skipped, not an
error - local books offer props for squad players a stats provider may not
cover.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.domain.entities.injury_status import InjuryStatus
from src.domain.entities.lineup_confirmation import LineupConfirmation
from src.domain.entities.player import Player
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.ports.value_bet_repository import ValueBetRepository
from src.domain.services.player_props.player_prop_detector import (
    PlayerPropDetection,
    PlayerPropDetector,
)


@dataclass(frozen=True, slots=True)
class DetectPlayerPropValueBetsUseCase:
    player_prop_detector: PlayerPropDetector
    value_bet_repository: ValueBetRepository

    async def execute(
        self,
        *,
        prop_markets: Sequence[PlayerPropMarket],
        recent_stats_by_player_id: Mapping[str, Sequence[PlayerMatchStats]],
        lineup_confirmations: Sequence[LineupConfirmation],
        injury_statuses: Sequence[InjuryStatus],
    ) -> list[PlayerPropDetection]:
        players_by_name = {c.player.name.casefold(): c.player for c in lineup_confirmations}
        players_by_name.update({i.player.name.casefold(): i.player for i in injury_statuses})
        lineup_by_player_id = {c.player.id: c for c in lineup_confirmations}
        injury_by_player_id = {i.player.id: i for i in injury_statuses}

        detections: list[PlayerPropDetection] = []
        for prop_market in prop_markets:
            player = _resolve_player(prop_market.player_name, players_by_name)
            if player is None:
                continue

            detection = self.player_prop_detector.detect(
                prop_market=prop_market,
                historical_stats=recent_stats_by_player_id.get(player.id, []),
                lineup_confirmation=lineup_by_player_id.get(player.id),
                injury_status=injury_by_player_id.get(player.id),
            )
            if detection is not None:
                await self.value_bet_repository.save(detection.value_bet)
                detections.append(detection)

        return detections


def _resolve_player(player_name: str, players_by_name: Mapping[str, Player]) -> Player | None:
    return players_by_name.get(player_name.casefold())
