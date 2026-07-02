"""De-vig (overround removal) strategies for a sharp bookmaker's market.

Every strategy takes the full set of `DecimalOdds` for one market's outcomes
(e.g. Home/Draw/Away for 1X2, in any consistent order) and returns fair
`Probability` objects in that same order, summing to 1.0. Strategy pattern:
`MarketValueDetector` is handed a `DevigStrategy` instance and never branches
on which method is in use.

All four methods agree exactly when there is no margin to remove (raw
implied probabilities already sum to 1.0) and, by symmetry, whenever every
outcome carries identical odds (the fair split must be 1/n regardless of
method) - see the "no-vig" and "symmetric" hand-verified test vectors.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.domain.services.market_model._bisection import bisect_root
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.probability import Probability

# Upper bound for Shin's z (the "insider trading" proportion): the model's
# own formula divides by 2*(1-z), so z=1 is a singularity. Real markets
# resolve to z far below this; the bound only needs to bracket a root safely.
_SHIN_Z_MAX = 1.0 - 1e-9
# Upper bound for the Power method's exponent k. Realistic overrounds solve
# for a small k just above 1; 100 leaves enormous headroom for even extreme
# input while keeping bisection cheap.
_POWER_K_MAX = 100.0


def _raw_implied_probabilities(odds: Sequence[DecimalOdds]) -> list[float]:
    if len(odds) < 2:
        raise ValueError("A market needs at least 2 outcomes to de-vig")
    return [1.0 / o.value for o in odds]


class DevigStrategy(ABC):
    """One overround-removal method. Stateless and pure."""

    @abstractmethod
    def devig(self, odds: Sequence[DecimalOdds]) -> list[Probability]: ...


class MultiplicativeDevig(DevigStrategy):
    """Basic normalization: p_i = (1/odd_i) / sum_j(1/odd_j).

    Removes the overround proportionally to each outcome's raw implied
    probability - the simplest and most common baseline method.
    """

    def devig(self, odds: Sequence[DecimalOdds]) -> list[Probability]:
        raw = _raw_implied_probabilities(odds)
        total = sum(raw)
        return [Probability(r / total) for r in raw]


class AdditiveDevig(DevigStrategy):
    """Subtracts an equal share of the overround from every outcome:
    p_i = (1/odd_i) - (sum_j(1/odd_j) - 1) / n.

    Known limitation (not a bug): subtracting an equal *absolute* share can
    push a longshot's raw probability negative in a heavily skewed market
    (one strong favorite, large overround relative to the longshot's raw
    share) - `Probability`'s own [0, 1] invariant rejects that rather than
    silently returning a nonsensical value. Multiplicative/Shin/Power have
    no such failure mode - see their docstrings/tests.
    """

    def devig(self, odds: Sequence[DecimalOdds]) -> list[Probability]:
        raw = _raw_implied_probabilities(odds)
        overround = sum(raw) - 1.0
        share = overround / len(raw)
        return [Probability(r - share) for r in raw]


class ShinDevig(DevigStrategy):
    """Shin's (1992/1993) model: attributes part of the overround to
    informed ("insider") money rather than uniform margin, correcting for
    the favorite-longshot bias plain normalization ignores.

    Solves for z (the insider-money proportion) such that

        p_i(z) = (sqrt(z^2 + 4(1-z)*pi_i^2/Sigma) - z) / (2*(1-z))

    sums to 1, where pi_i are the raw implied probabilities and
    Sigma = sum(pi_i). Requires Sigma >= 1 - the z in [0, 1) domain has no
    solution below that, since at z=0 the sum of p_i(0) is already
    sqrt(Sigma), which only reaches 1 when Sigma does (the no-vig case,
    solved exactly at z=0).
    """

    def devig(self, odds: Sequence[DecimalOdds]) -> list[Probability]:
        raw = _raw_implied_probabilities(odds)
        sigma = sum(raw)
        if sigma < 1.0:
            raise ValueError(
                "Shin's method requires a non-negative overround (raw implied "
                f"probabilities must sum to at least 1.0, got {sigma})"
            )

        def total_probability(z: float) -> float:
            return sum(self._shin_probability(z, pi, sigma) for pi in raw) - 1.0

        z = bisect_root(total_probability, 0.0, _SHIN_Z_MAX)
        return [Probability(self._shin_probability(z, pi, sigma)) for pi in raw]

    @staticmethod
    def _shin_probability(z: float, pi: float, sigma: float) -> float:
        return ((z**2 + 4.0 * (1.0 - z) * pi**2 / sigma) ** 0.5 - z) / (2.0 * (1.0 - z))


class PowerDevig(DevigStrategy):
    """Power (a.k.a. logarithmic) method: raises every raw implied
    probability to a common exponent k such that

        p_i = (1/odd_i)^k

    sums to 1 by construction, rather than normalizing afterwards. Because
    each raw probability is in (0, 1), p_i is monotonically decreasing in k,
    so there is exactly one k that removes the overround.
    """

    def devig(self, odds: Sequence[DecimalOdds]) -> list[Probability]:
        raw = _raw_implied_probabilities(odds)

        def total_probability(k: float) -> float:
            return sum(pi**k for pi in raw) - 1.0

        k = bisect_root(total_probability, 1e-9, _POWER_K_MAX)
        return [Probability(pi**k) for pi in raw]
