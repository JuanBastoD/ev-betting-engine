"""Backtesting/calibration metrics over settled bets: Brier score, log loss,
calibration curve, and average CLV - overall and segmented by market_type,
bookmaker, model_source, and (for player props) prop type.

Pure domain service: no I/O, deterministic given a list of `SettledBet`s.
`PUSH` results are excluded from Brier score/log loss (there is no
won/lost signal to score a probability against) but still counted in
`profit_loss`-oriented reporting elsewhere - this module only computes
probability-accuracy metrics, not P&L.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.domain.entities.bet_result import BetResult
from src.domain.entities.market_type import MarketType
from src.domain.entities.player_prop_type import PlayerPropType
from src.domain.entities.settled_bet import SettledBet

_LOG_LOSS_EPSILON = 1e-15
_DEFAULT_BUCKET_WIDTH = 0.1


@dataclass(frozen=True, slots=True)
class CalibrationBucket:
    """One predicted-probability range (e.g. [0.2, 0.3)) and how it
    compares to reality. `predicted_mean`/`observed_frequency` are `None`
    when no scoreable (non-push) settled bet falls in this range."""

    lower_bound: float
    upper_bound: float
    predicted_mean: float | None
    observed_frequency: float | None
    sample_size: int


@dataclass(frozen=True, slots=True)
class CalibrationMetrics:
    """`brier_score`/`log_loss` are `None` when `sample_size == 0` (no
    scoreable bets); `average_clv` is `None` when none of the settled bets
    in scope captured a closing sharp line."""

    sample_size: int
    brier_score: float | None
    log_loss: float | None
    average_clv: float | None
    calibration_curve: tuple[CalibrationBucket, ...]


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    overall: CalibrationMetrics
    by_market_type: Mapping[str, CalibrationMetrics]
    by_bookmaker: Mapping[str, CalibrationMetrics]
    by_model_source: Mapping[str, CalibrationMetrics]
    by_prop_type: Mapping[str, CalibrationMetrics]


class CalibrationService:
    def __init__(self, *, bucket_width: float = _DEFAULT_BUCKET_WIDTH) -> None:
        if not (0.0 < bucket_width <= 1.0):
            raise ValueError(f"bucket_width must be within (0.0, 1.0], got {bucket_width}")
        self._bucket_width = bucket_width

    def calculate(self, settled_bets: Sequence[SettledBet]) -> CalibrationMetrics:
        scoreable = [sb for sb in settled_bets if sb.result is not BetResult.PUSH]
        predictions = [sb.value_bet.fair_probability.value for sb in scoreable]
        outcomes = [1.0 if sb.result is BetResult.WON else 0.0 for sb in scoreable]

        clv_values = [sb.clv for sb in settled_bets if sb.clv is not None]

        return CalibrationMetrics(
            sample_size=len(scoreable),
            brier_score=_brier_score(predictions, outcomes),
            log_loss=_log_loss(predictions, outcomes),
            average_clv=(sum(clv_values) / len(clv_values)) if clv_values else None,
            calibration_curve=self._calibration_curve(predictions, outcomes),
        )

    def calculate_segmented(self, settled_bets: Sequence[SettledBet]) -> CalibrationReport:
        by_market_type: dict[str, list[SettledBet]] = {}
        by_bookmaker: dict[str, list[SettledBet]] = {}
        by_model_source: dict[str, list[SettledBet]] = {}
        by_prop_type: dict[str, list[SettledBet]] = {}

        for settled_bet in settled_bets:
            value_bet = settled_bet.value_bet
            by_market_type.setdefault(value_bet.selection.market_type.value, []).append(
                settled_bet
            )
            by_model_source.setdefault(value_bet.model_source.value, []).append(settled_bet)
            if value_bet.bookmaker is not None:
                by_bookmaker.setdefault(value_bet.bookmaker.name, []).append(settled_bet)
            if value_bet.selection.market_type is MarketType.PLAYER_PROP:
                prop_type = extract_prop_type(value_bet.selection.outcome)
                if prop_type is not None:
                    by_prop_type.setdefault(prop_type.value, []).append(settled_bet)

        return CalibrationReport(
            overall=self.calculate(settled_bets),
            by_market_type={k: self.calculate(v) for k, v in by_market_type.items()},
            by_bookmaker={k: self.calculate(v) for k, v in by_bookmaker.items()},
            by_model_source={k: self.calculate(v) for k, v in by_model_source.items()},
            by_prop_type={k: self.calculate(v) for k, v in by_prop_type.items()},
        )

    def _calibration_curve(
        self, predictions: Sequence[float], outcomes: Sequence[float]
    ) -> tuple[CalibrationBucket, ...]:
        num_buckets = round(1.0 / self._bucket_width)
        bucketed_predictions: list[list[float]] = [[] for _ in range(num_buckets)]
        bucketed_outcomes: list[list[float]] = [[] for _ in range(num_buckets)]

        for prediction, outcome in zip(predictions, outcomes):
            index = min(int(prediction / self._bucket_width), num_buckets - 1)
            bucketed_predictions[index].append(prediction)
            bucketed_outcomes[index].append(outcome)

        buckets = []
        for index in range(num_buckets):
            preds_in_bucket = bucketed_predictions[index]
            outcomes_in_bucket = bucketed_outcomes[index]
            buckets.append(
                CalibrationBucket(
                    lower_bound=index * self._bucket_width,
                    upper_bound=(index + 1) * self._bucket_width,
                    predicted_mean=_mean(preds_in_bucket),
                    observed_frequency=_mean(outcomes_in_bucket),
                    sample_size=len(preds_in_bucket),
                )
            )
        return tuple(buckets)


def extract_prop_type(outcome: str) -> PlayerPropType | None:
    """`Selection.outcome` for a PLAYER_PROP bet compresses
    "{player_name} {prop_type} {Over/Under}" into one string (Phase 8's
    `_selection_for`, since `Selection` has no player/prop-type field of
    its own) - this recovers the `PlayerPropType` token from it for
    calibration segmentation. Returns `None` if no known prop type appears
    (defensive - should not happen for a genuine PLAYER_PROP bet produced
    by `PlayerPropDetector`)."""
    tokens = outcome.split()
    for prop_type in PlayerPropType:
        if prop_type.value in tokens:
            return prop_type
    return None


def _brier_score(predictions: Sequence[float], outcomes: Sequence[float]) -> float | None:
    if not predictions:
        return None
    return sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / len(predictions)


def _log_loss(predictions: Sequence[float], outcomes: Sequence[float]) -> float | None:
    if not predictions:
        return None
    total = 0.0
    for p, o in zip(predictions, outcomes):
        clipped = min(max(p, _LOG_LOSS_EPSILON), 1.0 - _LOG_LOSS_EPSILON)
        total += o * math.log(clipped) + (1.0 - o) * math.log(1.0 - clipped)
    return -total / len(predictions)


def _mean(values: Sequence[float]) -> float | None:
    return (sum(values) / len(values)) if values else None
