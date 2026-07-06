"""EV calculation for player-prop bets.

Identical formula to `src.domain.services.market_model.ev_calculator` -
imported and reused directly, not reimplemented. `calculate_ev`,
`breakeven_odds` and `exceeds_ev_threshold` are re-exported unchanged so
callers in this package only need one import; `calculate_prop_ev` is the
one genuinely prop-specific addition, adapting the generic calculator to a
`PlayerPropMarket`'s own quoted odds instead of requiring the caller to
unpack `.odds` themselves.
"""

from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.services.market_model.ev_calculator import (
    breakeven_odds,
    calculate_ev,
    exceeds_ev_threshold,
)
from src.domain.value_objects.edge_percentage import EdgePercentage
from src.domain.value_objects.probability import Probability

__all__ = [
    "breakeven_odds",
    "calculate_ev",
    "calculate_prop_ev",
    "exceeds_ev_threshold",
]


def calculate_prop_ev(
    *, fair_probability: Probability, prop_market: PlayerPropMarket
) -> EdgePercentage:
    return calculate_ev(fair_probability=fair_probability, local_odds=prop_market.odds)
