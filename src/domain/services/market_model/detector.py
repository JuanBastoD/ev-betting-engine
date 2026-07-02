"""Orchestrates the market-model pipeline: de-vig the sharp market, price
every local quote against the resulting fair probabilities, and emit
`ValueBet`s for the ones that clear the EV threshold.

A pure domain service - no I/O, no repository/provider calls. Callers (a
future application-layer use case) are expected to fetch the sharp and local
`OddsQuote`s themselves and hand them to `detect()`.
"""

from collections.abc import Sequence

from src.domain.entities.market_type import MarketType
from src.domain.entities.model_source import ModelSource
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.value_bet import ValueBet
from src.domain.services.market_model.devig import DevigStrategy
from src.domain.services.market_model.ev_calculator import calculate_ev, exceeds_ev_threshold
from src.domain.services.market_model.kelly import kelly_stake
from src.domain.value_objects.probability import Probability


class MarketValueDetector:
    """Detects +EV local odds for one market (1X2 / Over-Under / BTTS)
    against a de-vigged sharp reference.

    `devig_strategy` is injected (Strategy pattern) rather than selected
    internally, so callers choose Multiplicative/Additive/Shin/Power without
    this class knowing the difference.
    """

    def __init__(
        self,
        devig_strategy: DevigStrategy,
        *,
        min_ev_threshold: float,
        kelly_fraction: float,
        max_kelly_fraction: float = 1.0,
    ) -> None:
        self._devig_strategy = devig_strategy
        self._min_ev_threshold = min_ev_threshold
        self._kelly_fraction = kelly_fraction
        self._max_kelly_fraction = max_kelly_fraction

    def detect(
        self, sharp_quotes: Sequence[OddsQuote], local_quotes: Sequence[OddsQuote]
    ) -> list[ValueBet]:
        """`sharp_quotes` must be every outcome of one sharp bookmaker's
        market for one match (e.g. Home/Draw/Away, all from Pinnacle,
        same match, same market_type+line) - that's what de-vigging one
        market means. `local_quotes` are priced against it; each must
        belong to the same match+market and to an outcome the sharp side
        also quoted, or this raises - mixing markets/matches is a caller
        bug, not something to silently drop.
        """
        if not sharp_quotes:
            raise ValueError("sharp_quotes must not be empty")

        match = sharp_quotes[0].match
        market_key = (sharp_quotes[0].selection.market_type, sharp_quotes[0].selection.line)
        for quote in sharp_quotes:
            self._require_same_market(quote, match_id=match.id, market_key=market_key)

        fair_probabilities = self._devig_strategy.devig([quote.odds for quote in sharp_quotes])
        fair_probability_by_outcome = {
            quote.selection.outcome: probability
            for quote, probability in zip(sharp_quotes, fair_probabilities)
        }

        value_bets: list[ValueBet] = []
        for local_quote in local_quotes:
            self._require_same_market(local_quote, match_id=match.id, market_key=market_key)
            fair_probability = self._fair_probability_for(
                local_quote, fair_probability_by_outcome
            )

            value_bet = self._try_build_value_bet(local_quote, fair_probability)
            if value_bet is not None:
                value_bets.append(value_bet)

        return value_bets

    def _try_build_value_bet(
        self, local_quote: OddsQuote, fair_probability: Probability
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
            # Reachable in practice only when kelly_fraction or
            # max_kelly_fraction is configured to 0 (staking suggestions
            # explicitly disabled) - positive EV alone always makes full
            # Kelly's f* > 0, so this isn't otherwise expected to trigger.
            return None

        return ValueBet(
            match=local_quote.match,
            selection=local_quote.selection,
            local_odds=local_quote.odds,
            fair_probability=fair_probability,
            edge=edge,
            suggested_stake=stake,
            model_source=ModelSource.MARKET,
        )

    @staticmethod
    def _require_same_market(
        quote: OddsQuote, *, match_id: str, market_key: tuple[MarketType, float | None]
    ) -> None:
        if quote.match.id != match_id:
            raise ValueError(
                f"All quotes must belong to match {match_id!r}, got {quote.match.id!r}"
            )
        quote_key = (quote.selection.market_type, quote.selection.line)
        if quote_key != market_key:
            raise ValueError(
                f"All quotes must belong to the same market {market_key!r}, got {quote_key!r}"
            )

    @staticmethod
    def _fair_probability_for(
        local_quote: OddsQuote, fair_probability_by_outcome: dict[str, Probability]
    ) -> Probability:
        fair_probability = fair_probability_by_outcome.get(local_quote.selection.outcome)
        if fair_probability is None:
            raise ValueError(
                f"No sharp quote for outcome {local_quote.selection.outcome!r}; "
                "cannot price this local quote"
            )
        return fair_probability
