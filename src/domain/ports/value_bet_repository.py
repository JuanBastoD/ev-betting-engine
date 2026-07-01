from abc import ABC, abstractmethod

from src.domain.entities.value_bet import ValueBet


class ValueBetRepository(ABC):
    """Persistence contract for detected `ValueBet` opportunities."""

    @abstractmethod
    async def save(self, value_bet: ValueBet) -> None: ...

    @abstractmethod
    async def list_by_match_id(self, match_id: str) -> list[ValueBet]: ...

    @abstractmethod
    async def list_all(self) -> list[ValueBet]: ...
