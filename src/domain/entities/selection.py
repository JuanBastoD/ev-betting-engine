from dataclasses import dataclass

from src.domain.entities.market_type import MarketType


@dataclass(frozen=True, slots=True)
class Selection:
    """A specific bettable outcome within a market.

    `line` carries the threshold for line-based markets (e.g. 2.5 for
    Over/Under 2.5) and is None for markets without a line, such as BTTS.
    """

    market_type: MarketType
    outcome: str
    line: float | None = None

    def __post_init__(self) -> None:
        if not self.outcome:
            raise ValueError("Selection.outcome must not be empty")
