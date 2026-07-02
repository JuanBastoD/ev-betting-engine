from abc import ABC, abstractmethod

from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.player_prop_market import PlayerPropMarket


class LocalOddsProvider(ABC):
    """Gateway to odds published by local/regional bookmakers being scanned for value.

    Covers both the main match markets (1X2, Over/Under, BTTS) and the
    player-prop markets a bookmaker may publish for the same fixture.
    """

    @abstractmethod
    async def get_odds(self, match: Match) -> list[OddsQuote]: ...

    @abstractmethod
    async def get_player_props(self, match: Match) -> list[PlayerPropMarket]: ...
