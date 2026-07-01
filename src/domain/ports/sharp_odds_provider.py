from abc import ABC, abstractmethod

from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote


class SharpOddsProvider(ABC):
    """Gateway to odds published by the reference sharp bookmaker."""

    @abstractmethod
    async def get_odds(self, match: Match) -> list[OddsQuote]: ...
