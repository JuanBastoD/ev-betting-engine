from abc import ABC, abstractmethod

from src.domain.entities.player import Player


class PlayerRepository(ABC):
    """Persistence contract for `Player` entities."""

    @abstractmethod
    async def get_by_id(self, player_id: str) -> Player | None: ...

    @abstractmethod
    async def list_by_team_id(self, team_id: str) -> list[Player]: ...

    @abstractmethod
    async def save(self, player: Player) -> None: ...
