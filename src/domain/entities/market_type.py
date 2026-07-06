from enum import Enum


class MarketType(str, Enum):
    """Supported pre-match betting markets."""

    MATCH_WINNER_1X2 = "MATCH_WINNER_1X2"
    OVER_UNDER = "OVER_UNDER"
    BTTS = "BTTS"
    PLAYER_PROP = "PLAYER_PROP"
