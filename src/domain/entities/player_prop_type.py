from enum import Enum


class PlayerPropType(str, Enum):
    """Supported player-proposition (prop) markets."""

    GOALS = "GOALS"
    SHOTS_ON_TARGET = "SHOTS_ON_TARGET"
    ASSISTS = "ASSISTS"
    CARDS = "CARDS"
