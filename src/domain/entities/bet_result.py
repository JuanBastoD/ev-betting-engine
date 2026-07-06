from enum import Enum


class BetResult(str, Enum):
    """The real-world outcome of a settled bet."""

    WON = "WON"
    LOST = "LOST"
    PUSH = "PUSH"
