from abc import ABC, abstractmethod

from src.domain.entities.settled_bet import SettledBet


class SettledBetRepository(ABC):
    """Persistence contract for settled (outcome-known) bets."""

    @abstractmethod
    async def save(self, settled_bet: SettledBet) -> None: ...

    @abstractmethod
    async def list_all(self) -> list[SettledBet]: ...
