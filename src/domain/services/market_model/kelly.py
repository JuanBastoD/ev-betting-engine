"""Fractional Kelly stake sizing.

Deliberately generic: takes only a probability, odds and the two sizing
knobs (fraction, cap) - nothing here is specific to the market/devig model,
so the future team-form and player-prop engines can size their own +EV bets
with the same function.

`Stake.amount` here is the recommended fraction of bankroll to wager (e.g.
0.025 = 2.5% of bankroll), not a currency amount: converting that fraction
into a concrete stake size requires knowing the user's actual bankroll,
which is an application-layer concern for a later phase. `Stake`'s own
invariant (amount > 0) forbids representing "no bet" as `Stake(0.0)`, so a
non-positive Kelly fraction returns `None` instead.
"""

from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.probability import Probability
from src.domain.value_objects.stake import Stake


def kelly_stake(
    *,
    probability: Probability,
    odds: DecimalOdds,
    kelly_fraction: float,
    max_fraction: float = 1.0,
) -> Stake | None:
    """f* = (b*p - q) / b, with b = odds - 1, p = probability, q = 1 - p.

    `kelly_fraction` scales full Kelly down (e.g. 0.25 for quarter-Kelly,
    matching `Settings.kelly_fraction`); `max_fraction` then caps the scaled
    result as a hard risk ceiling. Both must be in [0.0, 1.0]. Returns None
    (never a negative or zero Stake) whenever the sized fraction is <= 0.
    """
    if not (0.0 <= kelly_fraction <= 1.0):
        raise ValueError(f"kelly_fraction must be within [0.0, 1.0], got {kelly_fraction}")
    if not (0.0 <= max_fraction <= 1.0):
        raise ValueError(f"max_fraction must be within [0.0, 1.0], got {max_fraction}")

    b = odds.value - 1.0
    p = probability.value
    q = 1.0 - p
    full_kelly = (b * p - q) / b

    sized = full_kelly * kelly_fraction
    capped = min(sized, max_fraction)
    if capped <= 0.0:
        return None
    return Stake(capped)
