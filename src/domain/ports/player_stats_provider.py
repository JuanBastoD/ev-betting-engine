from abc import ABC, abstractmethod

from src.domain.entities.injury_status import InjuryStatus
from src.domain.entities.lineup_confirmation import LineupConfirmation
from src.domain.entities.player_match_stats import PlayerMatchStats


class PlayerStatsProvider(ABC):
    """Gateway to player-level data: recent match stats, injury reports, and
    lineup confirmations (official or, absent that, an estimate)."""

    @abstractmethod
    async def get_player_recent_matches(self, player_id: str, n: int = 10) -> list[PlayerMatchStats]: ...

    @abstractmethod
    async def get_injury_report(self, match_id: str) -> list[InjuryStatus]: ...

    @abstractmethod
    async def get_confirmed_lineup(self, match_id: str) -> list[LineupConfirmation]: ...
