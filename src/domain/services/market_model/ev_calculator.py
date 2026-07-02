"""Expected-value comparison of a fair (de-vigged) probability against a
local bookmaker's quoted odds.

Deliberately independent of `devig.py`: `calculate_ev` only needs a
`Probability`, wherever it came from - the future team-form and player-prop
statistical engines will call it directly with a model-derived probability
instead of a devig-derived one.
"""

from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.edge_percentage import EdgePercentage
from src.domain.value_objects.probability import Probability


def calculate_ev(*, fair_probability: Probability, local_odds: DecimalOdds) -> EdgePercentage:
    """EV per unit staked: fair_probability * local_odds - 1, expressed as a
    percentage (e.g. 0.10 -> EdgePercentage(10.0))."""
    ev_per_unit = fair_probability.value * local_odds.value - 1.0
    return EdgePercentage(ev_per_unit * 100.0)


def breakeven_odds(fair_probability: Probability) -> float:
    """The local odds at which betting this selection has exactly 0% edge
    (1 / fair_probability). A selection is +EV precisely when the local odds
    quoted exceed this value."""
    return 1.0 / fair_probability.value


def exceeds_ev_threshold(edge: EdgePercentage, *, min_ev_threshold: float) -> bool:
    """Whether `edge` clears the minimum-edge bar.

    `min_ev_threshold` is a fraction (e.g. 0.02 = 2%), matching
    `Settings.min_ev_threshold` - callers pass it in explicitly rather than
    this module reading config, keeping the domain free of infrastructure
    imports.
    """
    return edge.value > min_ev_threshold * 100.0
