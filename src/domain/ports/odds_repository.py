from abc import ABC, abstractmethod

from src.domain.entities.odds_quote import OddsQuote


class OddsRepository(ABC):
    """Persistence contract for `OddsQuote` entities."""

    @abstractmethod
    async def save(self, odds_quote: OddsQuote) -> None: ...

    @abstractmethod
    async def list_by_match_id(self, match_id: str) -> list[OddsQuote]: ...
