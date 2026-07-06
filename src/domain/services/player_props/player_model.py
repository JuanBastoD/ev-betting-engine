"""Player-prop Over/Under probability model.

Strategy pattern (`PlayerPropsModel`): `PlayerPropDetector` depends on the
interface, not on `PoissonPropsModel` specifically, so a future trained
model (Prompt 10) can be injected without touching the detector.

Deliberately self-contained: unlike `match_model`, this module does not
import `market_model`'s devig at all, and only reaches into `match_model`
for one narrow, explicitly-justified reuse (`opponent_factor_from_team_strength`
below) rather than depending on its Poisson machinery - the tiny Poisson
pmf/cdf helpers here are re-derived rather than imported from
`xg_model.py`, keeping the two statistical engines independently evolvable.
"""

import math
from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.domain.entities.injury_status_type import InjuryStatusType
from src.domain.entities.lineup_confirmation import LineupConfirmation
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_prop_type import PlayerPropType
from src.domain.services.match_model.team_strength import TeamStrength
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.probability import Probability

_DEFAULT_BENCH_MINUTES = 15.0


class PlayerPropsModel(ABC):
    """One way of turning a player's history into an Over/Under probability
    for a prop line. Stateless given its own configuration."""

    @abstractmethod
    def predict_probability(
        self,
        *,
        historical_stats: Sequence[PlayerMatchStats],
        prop_type: PlayerPropType,
        outcome: str,
        line: float,
        expected_minutes: float,
        opponent_strength_factor: float = 1.0,
    ) -> Probability: ...


class PoissonPropsModel(PlayerPropsModel):
    """Models the metric count as Poisson(lambda), with

        lambda = ewma_per_90_rate * (expected_minutes / minutes_baseline)
                 * opponent_strength_factor

    `ewma_per_90_rate` is an exponentially-weighted moving average (more
    weight on recent matches) of the player's historical per-90-minutes
    rate in `prop_type` - a plain average would weight a match from 10
    games ago the same as last week's, which is what Prompt 8 explicitly
    asks not to do.

    Negative Binomial (for over-dispersed metrics) is a natural second
    `PlayerPropsModel` implementation this Strategy interface leaves room
    for; only Poisson is implemented here.
    """

    def __init__(self, *, ewma_alpha: float = 0.3, minutes_baseline: float = 90.0) -> None:
        if not (0.0 < ewma_alpha <= 1.0):
            raise ValueError(f"ewma_alpha must be within (0.0, 1.0], got {ewma_alpha}")
        if minutes_baseline <= 0.0:
            raise ValueError(f"minutes_baseline must be positive, got {minutes_baseline}")
        self._ewma_alpha = ewma_alpha
        self._minutes_baseline = minutes_baseline

    def predict_probability(
        self,
        *,
        historical_stats: Sequence[PlayerMatchStats],
        prop_type: PlayerPropType,
        outcome: str,
        line: float,
        expected_minutes: float,
        opponent_strength_factor: float = 1.0,
    ) -> Probability:
        if line <= 0.0:
            raise ValueError(f"line must be positive, got {line}")
        if expected_minutes < 0.0:
            raise ValueError(f"expected_minutes must not be negative, got {expected_minutes}")
        if opponent_strength_factor < 0.0:
            raise ValueError(
                f"opponent_strength_factor must not be negative, got {opponent_strength_factor}"
            )
        if outcome not in ("Over", "Under"):
            raise ValueError(f"outcome must be 'Over' or 'Under', got {outcome!r}")

        per_90_rate = _ewma_per_90_rate(historical_stats, prop_type, alpha=self._ewma_alpha)
        lam = per_90_rate * (expected_minutes / self._minutes_baseline) * opponent_strength_factor

        over_probability = _clamp_unit(1.0 - _poisson_cdf(math.floor(line), lam))
        if outcome == "Over":
            return Probability(over_probability)
        return Probability(_clamp_unit(1.0 - over_probability))


def _metric_value(stats: PlayerMatchStats, prop_type: PlayerPropType) -> int:
    if prop_type is PlayerPropType.GOALS:
        return stats.goals
    if prop_type is PlayerPropType.SHOTS_ON_TARGET:
        return stats.shots_on_target
    if prop_type is PlayerPropType.ASSISTS:
        return stats.assists
    if prop_type is PlayerPropType.CARDS:
        return stats.yellow_cards + stats.red_cards
    raise ValueError(f"Unsupported prop type: {prop_type!r}")


def _ewma_per_90_rate(
    stats: Sequence[PlayerMatchStats], prop_type: PlayerPropType, *, alpha: float
) -> float:
    """`stats` must be ordered most-recent-first (index 0 = latest match).
    Matches with 0 minutes played are excluded - they carry no usable
    per-90 rate, not a rate of zero. Weight for index i is
    alpha*(1-alpha)**i, renormalized to sum to 1 over however many usable
    matches are actually supplied (a truncated EWMA series doesn't sum to
    exactly 1 on its own)."""
    usable = [s for s in stats if s.minutes_played > 0]
    if not usable:
        raise ValueError(
            "No historical_stats with minutes_played > 0 to compute a per-90 rate from"
        )

    per_90_rates = [_metric_value(s, prop_type) / s.minutes_played * 90.0 for s in usable]
    raw_weights = [alpha * (1.0 - alpha) ** i for i in range(len(usable))]
    total_weight = sum(raw_weights)
    return sum(w * r for w, r in zip(raw_weights, per_90_rates)) / total_weight


def expected_minutes_from_lineup(
    lineup_confirmation: LineupConfirmation | None,
    *,
    full_match_minutes: float = 90.0,
    bench_minutes: float = _DEFAULT_BENCH_MINUTES,
) -> float:
    """Blends `full_match_minutes` and `bench_minutes` by
    `start_probability`. A *confirmed* lineup slot (Prompt 4:
    `start_probability` is exactly 1.0 or 0.0 whenever `is_confirmed`) then
    collapses this to exactly one or the other; an unconfirmed/estimated
    probability smoothly interpolates.

    With no `LineupConfirmation` at all, assumes a full match: there is no
    signal either way, and assuming reduced minutes the data doesn't
    support would be worse than assuming a normal appearance (mirrors
    `estimate_start_probability`'s Prompt-4 stance of not asserting absence
    without evidence).
    """
    if lineup_confirmation is None:
        return full_match_minutes
    p = lineup_confirmation.start_probability.value
    return p * full_match_minutes + (1.0 - p) * bench_minutes


def confidence_penalty(
    *,
    lineup_confirmed: bool,
    player_status: InjuryStatusType,
    unconfirmed_lineup_penalty: float = 0.5,
    doubtful_or_injured_penalty: float = 0.5,
) -> float:
    """A multiplier in [0.0, 1.0] fed into `confidence_adjusted_probability`
    below - 1.0 means full confidence (no discount). Two independent,
    compounding triggers: `lineup_confirmed=False` (the minutes estimate is
    just that, an estimate) and `player_status` in
    {DOUBTFUL, INJURED, SUSPENDED} (the player might not feature at all, a
    distinct risk from "how many minutes will they get"). Both factors are
    plain, documented configuration - not fitted from data.
    """
    if not (0.0 <= unconfirmed_lineup_penalty <= 1.0):
        raise ValueError(
            f"unconfirmed_lineup_penalty must be within [0.0, 1.0], got {unconfirmed_lineup_penalty}"
        )
    if not (0.0 <= doubtful_or_injured_penalty <= 1.0):
        raise ValueError(
            f"doubtful_or_injured_penalty must be within [0.0, 1.0], got {doubtful_or_injured_penalty}"
        )

    penalty = 1.0
    if not lineup_confirmed:
        penalty *= 1.0 - unconfirmed_lineup_penalty
    if player_status in (
        InjuryStatusType.DOUBTFUL,
        InjuryStatusType.INJURED,
        InjuryStatusType.SUSPENDED,
    ):
        penalty *= 1.0 - doubtful_or_injured_penalty
    return penalty


def confidence_adjusted_probability(
    *, model_probability: Probability, local_odds: DecimalOdds, confidence: float
) -> Probability:
    """Blends `model_probability` toward the odds' own breakeven probability
    (1/odds, i.e. "assume zero edge") by `1 - confidence`.

    This is algebraically equivalent to discounting `calculate_ev`'s
    resulting edge by `confidence` (full confidence keeps the model's
    probability as-is; zero confidence collapses to "no edge at all", which
    then correctly fails any positive EV threshold) - expressed as a
    probability blend, not a post-hoc edge multiplication, so it can be fed
    straight into `calculate_ev`/`kelly_stake` unchanged and stays
    internally consistent with whatever `ValueBet.edge`/`suggested_stake`
    end up being. Being a convex combination of two values already in
    [0, 1], the result needs no separate clamping.
    """
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence must be within [0.0, 1.0], got {confidence}")
    breakeven_probability = 1.0 / local_odds.value
    return Probability(
        confidence * model_probability.value + (1.0 - confidence) * breakeven_probability
    )


def opponent_factor_from_team_strength(opponent_strength: TeamStrength) -> float:
    """For the GOALS prop type specifically: `TeamStrength.defense` (Prompt
    7) is already calibrated against league-average GOALS, the same metric
    a GOALS prop counts - so it doubles directly as the multiplicative
    opponent factor (`defense` > 1.0 means the opponent concedes more goals
    than average, scaling the player's expected goal involvement up).

    For SHOTS_ON_TARGET/ASSISTS/CARDS, `TeamStrength` is calibrated on
    goals, not those metrics, so it is *not* a valid substitute for them -
    pricing those props needs its own opponent-strength figure from
    elsewhere (out of scope here, since no shots/cards team-strength model
    exists yet); `opponent_strength_factor` simply defaults to 1.0
    (neutral) in that case.
    """
    return opponent_strength.defense


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)


def _poisson_cdf(k: int, lam: float) -> float:
    return sum(_poisson_pmf(i, lam) for i in range(k + 1))


def _clamp_unit(value: float) -> float:
    return min(max(value, 0.0), 1.0)
