from dataclasses import dataclass
from datetime import datetime, timedelta

from src.domain.entities.bet_result import BetResult
from src.domain.entities.value_bet import ValueBet
from src.domain.value_objects.decimal_odds import DecimalOdds


@dataclass(frozen=True, slots=True)
class SettledBet:
    """A `ValueBet` paired with its real-world outcome, for backtesting and
    calibration (Prompt 10). Nests the full `ValueBet` (same convention as
    `PlayerMatchStats.match: Match`) rather than a bare reference, so a
    settled bet is self-contained - no second lookup needed to know what
    was actually bet on.

    `closing_sharp_odds` is the sharp (Pinnacle) price for this exact
    selection just before kickoff, captured for CLV (Closing Line Value) -
    `None` when no closing snapshot was captured for this bet.
    """

    value_bet: ValueBet
    result: BetResult
    settled_at: datetime
    closing_sharp_odds: DecimalOdds | None = None

    def __post_init__(self) -> None:
        if self.settled_at.tzinfo is None:
            raise ValueError("SettledBet.settled_at must be timezone-aware (UTC)")
        if self.settled_at.utcoffset() != timedelta(0):
            raise ValueError("SettledBet.settled_at must be expressed in UTC")

    @property
    def profit_loss(self) -> float:
        """In the same unit as `value_bet.suggested_stake.amount` (a
        fraction of bankroll, per Kelly's own convention) - WON returns
        stake*(odds-1), LOST returns -stake, PUSH (stake refunded) returns
        0.0.
        """
        stake = self.value_bet.suggested_stake.amount
        if self.result is BetResult.WON:
            return stake * (self.value_bet.local_odds.value - 1.0)
        if self.result is BetResult.LOST:
            return -stake
        return 0.0

    @property
    def clv(self) -> float | None:
        """Closing Line Value: the closing sharp line's implied probability
        minus the implied probability of the odds actually bet. Positive
        means the market moved toward the bettor's side after the bet was
        placed (a genuine edge signal, independent of whether this
        particular bet won or lost) - `None` when no closing line was
        captured for this bet.
        """
        if self.closing_sharp_odds is None:
            return None
        return (
            self.closing_sharp_odds.implied_probability
            - self.value_bet.local_odds.implied_probability
        )
