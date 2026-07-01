from abc import ABC, abstractmethod

from src.domain.entities.player_match_stats import PlayerMatchStats


class PlayerStatsRepository(ABC):
    """Persistence contract for `PlayerMatchStats` entities."""

    @abstractmethod
    async def save(self, stats: PlayerMatchStats) -> None: ...

    @abstractmethod
    async def list_by_player_id(self, player_id: str) -> list[PlayerMatchStats]: ...

    @abstractmethod
    async def list_by_match_id(self, match_id: str) -> list[PlayerMatchStats]: ...
