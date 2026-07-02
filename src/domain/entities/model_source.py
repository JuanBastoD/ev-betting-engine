from enum import Enum


class ModelSource(str, Enum):
    """Which probability model produced a ValueBet.

    MARKET: fair probabilities derived from de-vigged sharp (Pinnacle) odds.
    MATCH_STATS / PLAYER_PROPS: reserved for the future statistical engines
    (team-form model and player-prop model respectively).
    """

    MARKET = "MARKET"
    MATCH_STATS = "MATCH_STATS"
    PLAYER_PROPS = "PLAYER_PROPS"
