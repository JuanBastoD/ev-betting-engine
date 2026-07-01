from abc import ABC, abstractmethod

from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote


class LocalOddsProvider(ABC):
    """Gateway to odds published by local/regional bookmakers being scanned for value."""

    @abstractmethod
    async def get_odds(self, match: Match) -> list[OddsQuote]: ...
