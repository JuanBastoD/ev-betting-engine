from abc import ABC, abstractmethod

from src.domain.entities.match import Match


class MatchRepository(ABC):
    """Persistence contract for `Match` entities."""

    @abstractmethod
    async def get_by_id(self, match_id: str) -> Match | None: ...

    @abstractmethod
    async def list_upcoming(self) -> list[Match]: ...

    @abstractmethod
    async def save(self, match: Match) -> None: ...
