from enum import Enum


class InjuryStatusType(str, Enum):
    """A player's current fitness/availability state."""

    FIT = "FIT"
    DOUBTFUL = "DOUBTFUL"
    INJURED = "INJURED"
    SUSPENDED = "SUSPENDED"
