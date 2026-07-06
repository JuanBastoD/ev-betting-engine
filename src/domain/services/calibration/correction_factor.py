"""Explicit, auditable probability-correction factors derived from
calibration data - "the props model for shots-on-target is overestimating
by 8%, scale down" becomes a persisted, versioned `CorrectionFactor` a
future pipeline pass can apply *before* `calculate_ev`, without touching
the underlying statistical model at all.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.domain.entities.bet_result import BetResult
from src.domain.entities.market_type import MarketType
from src.domain.entities.settled_bet import SettledBet
from src.domain.services.calibration.calibration_service import extract_prop_type
from src.domain.value_objects.probability import Probability

_OVERALL_SEGMENT_TYPE = "overall"


@dataclass(frozen=True, slots=True)
class CorrectionFactor:
    """`factor` is a multiplier applied directly to a predicted
    `Probability` (see `apply_correction_factor`): `factor < 1.0` means the
    model has been overestimating this segment's probabilities (scale
    down), `factor > 1.0` means underestimating (scale up). `segment_type`
    is one of "overall"/"market_type"/"bookmaker"/"model_source"/
    "prop_type"; `segment_value` is the specific value within it (e.g.
    "PLAYER_PROP", "Betplay", "STATISTICAL", "SHOTS_ON_TARGET", or
    "overall" for the "overall" segment_type).

    Every computation persists a *new* row (`computed_at` timestamp) rather
    than overwriting the last one - "versioned" per Prompt 10 - so the
    correction history for a segment can be audited over time, not just the
    current value.
    """

    segment_type: str
    segment_value: str
    factor: float
    sample_size: int
    computed_at: datetime
    data_range_start: datetime
    data_range_end: datetime

    def __post_init__(self) -> None:
        if self.factor <= 0.0:
            raise ValueError(f"CorrectionFactor.factor must be positive, got {self.factor}")
        if self.sample_size < 0:
            raise ValueError(
                f"CorrectionFactor.sample_size must not be negative, got {self.sample_size}"
            )
        for field_name in ("computed_at", "data_range_start", "data_range_end"):
            value: datetime = getattr(self, field_name)
            if value.tzinfo is None:
                raise ValueError(f"CorrectionFactor.{field_name} must be timezone-aware (UTC)")
            if value.utcoffset() != timedelta(0):
                raise ValueError(f"CorrectionFactor.{field_name} must be expressed in UTC")
        if self.data_range_start > self.data_range_end:
            raise ValueError(
                "CorrectionFactor.data_range_start must not be after data_range_end"
            )


class CorrectionFactorService:
    """Computes one `CorrectionFactor` per segment with enough settled-bet
    volume to trust: `factor = observed_frequency / predicted_mean` over
    that segment's non-push settled bets (a segment predicting well has a
    factor near 1.0 by construction). Segments with fewer than
    `min_sample_size` settled bets are skipped rather than fabricating a
    correction from too little evidence.
    """

    def __init__(self, *, min_sample_size: int = 30) -> None:
        if min_sample_size < 1:
            raise ValueError(f"min_sample_size must be at least 1, got {min_sample_size}")
        self._min_sample_size = min_sample_size

    def compute_factors(
        self, settled_bets: Sequence[SettledBet], *, computed_at: datetime
    ) -> list[CorrectionFactor]:
        segments: dict[tuple[str, str], list[SettledBet]] = {
            (_OVERALL_SEGMENT_TYPE, _OVERALL_SEGMENT_TYPE): list(settled_bets)
        }
        for settled_bet in settled_bets:
            value_bet = settled_bet.value_bet
            segments.setdefault(
                ("market_type", value_bet.selection.market_type.value), []
            ).append(settled_bet)
            segments.setdefault(("model_source", value_bet.model_source.value), []).append(
                settled_bet
            )
            if value_bet.bookmaker is not None:
                segments.setdefault(("bookmaker", value_bet.bookmaker.name), []).append(
                    settled_bet
                )
            if value_bet.selection.market_type is MarketType.PLAYER_PROP:
                prop_type = extract_prop_type(value_bet.selection.outcome)
                if prop_type is not None:
                    segments.setdefault(("prop_type", prop_type.value), []).append(settled_bet)

        factors: list[CorrectionFactor] = []
        for (segment_type, segment_value), segment_bets in segments.items():
            factor = self._factor_for_segment(
                segment_type, segment_value, segment_bets, computed_at=computed_at
            )
            if factor is not None:
                factors.append(factor)
        return factors

    def _factor_for_segment(
        self,
        segment_type: str,
        segment_value: str,
        settled_bets: Sequence[SettledBet],
        *,
        computed_at: datetime,
    ) -> CorrectionFactor | None:
        scoreable = [sb for sb in settled_bets if sb.result is not BetResult.PUSH]
        if len(scoreable) < self._min_sample_size:
            return None

        predicted_mean = sum(sb.value_bet.fair_probability.value for sb in scoreable) / len(
            scoreable
        )
        observed_frequency = sum(1 for sb in scoreable if sb.result is BetResult.WON) / len(
            scoreable
        )
        if predicted_mean <= 0.0:
            return None  # nothing to divide by - degenerate segment, skip rather than raise

        settled_ats = [sb.settled_at for sb in scoreable]
        return CorrectionFactor(
            segment_type=segment_type,
            segment_value=segment_value,
            factor=observed_frequency / predicted_mean,
            sample_size=len(scoreable),
            computed_at=computed_at,
            data_range_start=min(settled_ats),
            data_range_end=max(settled_ats),
        )


def apply_correction_factor(probability: Probability, factor: CorrectionFactor) -> Probability:
    """Applies `factor` as a plain multiplier, clamped back into [0, 1] -
    the explicit, auditable adjustment step Prompt 10 asks for, meant to
    run *before* `calculate_ev`, never inside the statistical model itself.
    """
    adjusted = probability.value * factor.factor
    return Probability(min(max(adjusted, 0.0), 1.0))


def latest_by_segment(factors: Sequence[CorrectionFactor]) -> list[CorrectionFactor]:
    """Keeps only the most recently `computed_at` factor per
    (segment_type, segment_value) - correction factors are versioned
    (every computation adds new rows), so "the current factor" for a
    segment means the latest one on file."""
    latest: dict[tuple[str, str], CorrectionFactor] = {}
    for factor in factors:
        key = (factor.segment_type, factor.segment_value)
        current = latest.get(key)
        if current is None or factor.computed_at > current.computed_at:
            latest[key] = factor
    return list(latest.values())
