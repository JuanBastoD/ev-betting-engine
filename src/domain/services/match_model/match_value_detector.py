"""Orchestrates the match-statistics pipeline against the market model,
applying a configurable double-confirmation policy.

Reuses `MarketValueDetector.fair_probabilities`/`require_same_market`
(Prompt 6) for the market side rather than re-deriving devig/validation
logic, and `calculate_ev`/`exceeds_ev_threshold`/`kelly_stake` for pricing -
this module only adds the statistical prediction and the confirmation
policy on top.
"""

from collections.abc import Sequence
from enum import Enum

from src.domain.entities.market_type import MarketType
from src.domain.entities.model_source import ModelSource
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.selection import Selection
from src.domain.entities.value_bet import ValueBet
from src.domain.services.market_model.detector import MarketValueDetector
from src.domain.services.market_model.ev_calculator import calculate_ev, exceeds_ev_threshold
from src.domain.services.market_model.kelly import kelly_stake
from src.domain.services.match_model.team_strength import TeamStrength
from src.domain.services.match_model.xg_model import MatchProbabilities, MatchStatisticalModel
from src.domain.value_objects.probability import Probability


class ConfirmationMode(str, Enum):
    """CONFIRMATION (default): a selection only becomes a ValueBet when
    BOTH the market and the statistical model independently find it +EV
    above the threshold. INDEPENDENT: the statistical model's own opinion
    is enough, with no requirement that Pinnacle agrees."""

    CONFIRMATION = "CONFIRMATION"
    INDEPENDENT = "INDEPENDENT"


class MatchValueDetector:
    def __init__(
        self,
        statistical_model: MatchStatisticalModel,
        market_detector: MarketValueDetector,
        *,
        min_ev_threshold: float,
        kelly_fraction: float,
        max_kelly_fraction: float = 1.0,
        mode: ConfirmationMode = ConfirmationMode.CONFIRMATION,
        market_weight: float = 0.5,
    ) -> None:
        if not (0.0 <= market_weight <= 1.0):
            raise ValueError(f"market_weight must be within [0.0, 1.0], got {market_weight}")
        self._statistical_model = statistical_model
        self._market_detector = market_detector
        self._min_ev_threshold = min_ev_threshold
        self._kelly_fraction = kelly_fraction
        self._max_kelly_fraction = max_kelly_fraction
        self._mode = mode
        self._market_weight = market_weight

    @property
    def mode(self) -> ConfirmationMode:
        """Public so orchestrators pricing several markets per match (e.g.
        a use case grouping quotes by market before calling `detect()` once
        per group) can tell whether a market with no sharp coverage should
        be skipped (CONFIRMATION - nothing to confirm against) or still
        priced (INDEPENDENT - sharp_quotes was never required)."""
        return self._mode

    def detect(
        self,
        *,
        home_strength: TeamStrength,
        away_strength: TeamStrength,
        league_average_goals: float,
        local_quotes: Sequence[OddsQuote],
        sharp_quotes: Sequence[OddsQuote] | None = None,
    ) -> list[ValueBet]:
        """`sharp_quotes` is required in CONFIRMATION mode (there is nothing
        to confirm against without it) and ignored in INDEPENDENT mode.
        Every `local_quote` is priced against the statistical model's
        prediction for its `Selection`; unsupported market types (anything
        other than 1X2/BTTS/Over-Under, or an Over/Under line the model
        wasn't configured for) raise, same "caller bug" philosophy as
        `MarketValueDetector`.
        """
        probabilities = self._statistical_model.predict_match_probabilities(
            home_strength, away_strength, league_average_goals=league_average_goals
        )

        if self._mode is ConfirmationMode.INDEPENDENT:
            return self._detect_independent(local_quotes, probabilities)
        return self._detect_with_confirmation(local_quotes, probabilities, sharp_quotes)

    def _detect_independent(
        self, local_quotes: Sequence[OddsQuote], probabilities: MatchProbabilities
    ) -> list[ValueBet]:
        value_bets: list[ValueBet] = []
        for local_quote in local_quotes:
            statistical_probability = _statistical_probability_for(
                local_quote.selection, probabilities
            )
            value_bet = self._try_build_value_bet(
                local_quote, statistical_probability, ModelSource.STATISTICAL
            )
            if value_bet is not None:
                value_bets.append(value_bet)
        return value_bets

    def _detect_with_confirmation(
        self,
        local_quotes: Sequence[OddsQuote],
        probabilities: MatchProbabilities,
        sharp_quotes: Sequence[OddsQuote] | None,
    ) -> list[ValueBet]:
        if not sharp_quotes:
            raise ValueError(
                "sharp_quotes is required in CONFIRMATION mode - there is nothing to "
                "confirm the statistical model's opinion against without it"
            )

        market_fair_probability_by_outcome = self._market_detector.fair_probabilities(
            sharp_quotes
        )
        match_id = sharp_quotes[0].match.id
        market_key = (sharp_quotes[0].selection.market_type, sharp_quotes[0].selection.line)

        value_bets: list[ValueBet] = []
        for local_quote in local_quotes:
            MarketValueDetector.require_same_market(
                local_quote, match_id=match_id, market_key=market_key
            )
            market_probability = market_fair_probability_by_outcome.get(
                local_quote.selection.outcome
            )
            if market_probability is None:
                raise ValueError(
                    f"No sharp quote for outcome {local_quote.selection.outcome!r}; "
                    "cannot confirm this local quote against the market"
                )
            statistical_probability = _statistical_probability_for(
                local_quote.selection, probabilities
            )

            market_edge = calculate_ev(
                fair_probability=market_probability, local_odds=local_quote.odds
            )
            statistical_edge = calculate_ev(
                fair_probability=statistical_probability, local_odds=local_quote.odds
            )
            market_agrees = exceeds_ev_threshold(
                market_edge, min_ev_threshold=self._min_ev_threshold
            )
            statistical_agrees = exceeds_ev_threshold(
                statistical_edge, min_ev_threshold=self._min_ev_threshold
            )
            if not (market_agrees and statistical_agrees):
                continue

            # EV is linear in probability (calculate_ev = p*odds - 1), so a
            # weighted blend of two probabilities that each individually
            # clear the threshold against these same odds is mathematically
            # guaranteed to clear it too - no need to recheck the blend.
            blended_probability = Probability(
                self._market_weight * market_probability.value
                + (1.0 - self._market_weight) * statistical_probability.value
            )
            value_bet = self._try_build_value_bet(
                local_quote, blended_probability, ModelSource.BOTH
            )
            if value_bet is not None:
                value_bets.append(value_bet)

        return value_bets

    def _try_build_value_bet(
        self, local_quote: OddsQuote, fair_probability: Probability, model_source: ModelSource
    ) -> ValueBet | None:
        edge = calculate_ev(fair_probability=fair_probability, local_odds=local_quote.odds)
        if not exceeds_ev_threshold(edge, min_ev_threshold=self._min_ev_threshold):
            return None

        stake = kelly_stake(
            probability=fair_probability,
            odds=local_quote.odds,
            kelly_fraction=self._kelly_fraction,
            max_fraction=self._max_kelly_fraction,
        )
        if stake is None:
            return None

        return ValueBet(
            match=local_quote.match,
            selection=local_quote.selection,
            local_odds=local_quote.odds,
            fair_probability=fair_probability,
            edge=edge,
            suggested_stake=stake,
            model_source=model_source,
            bookmaker=local_quote.bookmaker,
        )


def _statistical_probability_for(
    selection: Selection, probabilities: MatchProbabilities
) -> Probability:
    if selection.market_type is MarketType.MATCH_WINNER_1X2:
        if selection.outcome == "Home":
            return probabilities.home_win
        if selection.outcome == "Draw":
            return probabilities.draw
        if selection.outcome == "Away":
            return probabilities.away_win
        raise ValueError(f"Unsupported 1X2 outcome for statistical pricing: {selection.outcome!r}")

    if selection.market_type is MarketType.BTTS:
        if selection.outcome == "Yes":
            return probabilities.btts_yes
        if selection.outcome == "No":
            return probabilities.btts_no
        raise ValueError(f"Unsupported BTTS outcome for statistical pricing: {selection.outcome!r}")

    if selection.market_type is MarketType.OVER_UNDER:
        over_under = probabilities.over_under_for_line(selection.line)
        if selection.outcome == "Over":
            return over_under.over
        if selection.outcome == "Under":
            return over_under.under
        raise ValueError(
            f"Unsupported Over/Under outcome for statistical pricing: {selection.outcome!r}"
        )

    raise ValueError(f"Unsupported market type for statistical pricing: {selection.market_type!r}")
