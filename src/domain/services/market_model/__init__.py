"""Market-model quantitative core: de-vig sharp odds, price the resulting fair
probability against a local quote, and size a Kelly stake.

Pure domain service - no infrastructure, no I/O, fully deterministic. This is
the first of what will eventually be several probability-model engines (team
form / player-prop stats are the other two envisioned in `ModelSource`); the
EV and Kelly building blocks are written to be reused by those, not just by
`MarketValueDetector`.
"""

from src.domain.services.market_model.detector import MarketValueDetector
from src.domain.services.market_model.devig import (
    AdditiveDevig,
    DevigStrategy,
    MultiplicativeDevig,
    PowerDevig,
    ShinDevig,
)
from src.domain.services.market_model.ev_calculator import (
    breakeven_odds,
    calculate_ev,
    exceeds_ev_threshold,
)
from src.domain.services.market_model.kelly import kelly_stake

__all__ = [
    "AdditiveDevig",
    "DevigStrategy",
    "MarketValueDetector",
    "MultiplicativeDevig",
    "PowerDevig",
    "ShinDevig",
    "breakeven_odds",
    "calculate_ev",
    "exceeds_ev_threshold",
    "kelly_stake",
]
