from enum import Enum


class PlayerPosition(str, Enum):
    """Broad on-pitch role. UNKNOWN covers providers that omit or don't
    recognize a position for a given player rather than forcing a guess."""

    GOALKEEPER = "GOALKEEPER"
    DEFENDER = "DEFENDER"
    MIDFIELDER = "MIDFIELDER"
    FORWARD = "FORWARD"
    UNKNOWN = "UNKNOWN"
