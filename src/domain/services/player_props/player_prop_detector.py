"""Orchestrates the player-prop pipeline: run the statistical model, apply
the confidence penalty, price against the local bookmaker's quoted odds,
and size a Kelly stake - reusing `kelly_stake` (Prompt 6) and
`calculate_prop_ev`/`exceeds_ev_threshold` (this package's thin wrapper
around Prompt 6's `ev_calculator`) rather than duplicating either.

`ValueBet.lineup_confirmed` (Phase 9: added once a concrete need - the
`GET /value-bets` listing endpoint reading persisted bets back out - made
"flag, don't silently extend" no longer the right call) carries this
signal on the persisted entity itself. `PlayerPropDetection` still wraps
it alongside the plain numeric `confidence` penalty (which has nowhere on
`ValueBet` to go, and isn't needed there - it's already reflected in the
discounted `fair_probability`/`edge`), so callers acting immediately on a
fresh detection don't need a repository round-trip to see either.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.entities.injury_status import InjuryStatus
from src.domain.entities.injury_status_type import InjuryStatusType
from src.domain.entities.lineup_confirmation import LineupConfirmation
from src.domain.entities.market_type import MarketType
from src.domain.entities.model_source import ModelSource
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.entities.selection import Selection
from src.domain.entities.value_bet import ValueBet
from src.domain.services.market_model.kelly import kelly_stake
from src.domain.services.player_props.player_model import (
    PlayerPropsModel,
    confidence_adjusted_probability,
    confidence_penalty,
    expected_minutes_from_lineup,
)
from src.domain.services.player_props.prop_ev_calculator import (
    calculate_prop_ev,
    exceeds_ev_threshold,
)


@dataclass(frozen=True, slots=True)
class PlayerPropDetection:
    """A detected +EV player-prop bet, paired with how reliable its inputs
    were - `lineup_confirmed`/`confidence` describe the *inputs* to
    `value_bet`, they are not fields on it."""

    value_bet: ValueBet
    lineup_confirmed: bool
    confidence: float


class PlayerPropDetector:
    def __init__(
        self,
        model: PlayerPropsModel,
        *,
        min_ev_threshold: float,
        kelly_fraction: float,
        max_kelly_fraction: float = 1.0,
        unconfirmed_lineup_penalty: float = 0.5,
        doubtful_or_injured_penalty: float = 0.5,
    ) -> None:
        self._model = model
        self._min_ev_threshold = min_ev_threshold
        self._kelly_fraction = kelly_fraction
        self._max_kelly_fraction = max_kelly_fraction
        self._unconfirmed_lineup_penalty = unconfirmed_lineup_penalty
        self._doubtful_or_injured_penalty = doubtful_or_injured_penalty

    def detect(
        self,
        *,
        prop_market: PlayerPropMarket,
        historical_stats: Sequence[PlayerMatchStats],
        lineup_confirmation: LineupConfirmation | None = None,
        injury_status: InjuryStatus | None = None,
        opponent_strength_factor: float = 1.0,
    ) -> PlayerPropDetection | None:
        """`prop_market` must be a line-based Over/Under prop (`line` is not
        None) - lineless props (e.g. "anytime scorer") are out of scope for
        this Poisson-line model, and raise. With no `lineup_confirmation`/
        `injury_status` given, assumes a full match and FIT respectively
        (no signal, no assumption of trouble - matches
        `expected_minutes_from_lineup`'s own stance).
        """
        if prop_market.line is None:
            raise ValueError(
                "PlayerPropDetector only prices line-based (Over/Under) props, "
                f"got a lineless market for {prop_market.player_name!r}"
            )

        expected_minutes = expected_minutes_from_lineup(lineup_confirmation)
        model_probability = self._model.predict_probability(
            historical_stats=historical_stats,
            prop_type=prop_market.prop_type,
            outcome=prop_market.outcome,
            line=prop_market.line,
            expected_minutes=expected_minutes,
            opponent_strength_factor=opponent_strength_factor,
        )

        # Absence of a LineupConfirmation is itself a reason for reduced
        # confidence (there's no lineup signal at all) - a different
        # question from expected_minutes_from_lineup's "no data -> assume a
        # normal appearance", which is about not asserting unsupported doubt.
        lineup_confirmed = (
            lineup_confirmation.is_confirmed if lineup_confirmation is not None else False
        )
        player_status = injury_status.status if injury_status is not None else InjuryStatusType.FIT

        confidence = confidence_penalty(
            lineup_confirmed=lineup_confirmed,
            player_status=player_status,
            unconfirmed_lineup_penalty=self._unconfirmed_lineup_penalty,
            doubtful_or_injured_penalty=self._doubtful_or_injured_penalty,
        )
        effective_probability = confidence_adjusted_probability(
            model_probability=model_probability,
            local_odds=prop_market.odds,
            confidence=confidence,
        )

        edge = calculate_prop_ev(fair_probability=effective_probability, prop_market=prop_market)
        if not exceeds_ev_threshold(edge, min_ev_threshold=self._min_ev_threshold):
            return None

        stake = kelly_stake(
            probability=effective_probability,
            odds=prop_market.odds,
            kelly_fraction=self._kelly_fraction,
            max_fraction=self._max_kelly_fraction,
        )
        if stake is None:
            return None

        value_bet = ValueBet(
            match=prop_market.match,
            selection=_selection_for(prop_market),
            local_odds=prop_market.odds,
            fair_probability=effective_probability,
            edge=edge,
            suggested_stake=stake,
            model_source=ModelSource.STATISTICAL,
            lineup_confirmed=lineup_confirmed,
        )
        return PlayerPropDetection(
            value_bet=value_bet, lineup_confirmed=lineup_confirmed, confidence=confidence
        )


def _selection_for(prop_market: PlayerPropMarket) -> Selection:
    """`Selection.outcome` is a plain descriptive string with no player
    reference of its own (same shape every other market's `ValueBet` uses)
    - compressing player name + prop type + Over/Under into it keeps
    `ValueBet` completely unchanged ("no fragmentar el resto del sistema"),
    at the cost of that identity only being recoverable by parsing this
    string. A first-class player reference on `Selection`/`ValueBet` would
    be the clean fix, flagged here rather than done, same as the
    `ValueBet`-has-no-bookmaker gap.
    """
    outcome = f"{prop_market.player_name} {prop_market.prop_type.value} {prop_market.outcome}"
    return Selection(market_type=MarketType.PLAYER_PROP, outcome=outcome, line=prop_market.line)
