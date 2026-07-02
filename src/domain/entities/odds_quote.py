from dataclasses import dataclass
from datetime import datetime, timedelta

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.match import Match
from src.domain.entities.selection import Selection
from src.domain.value_objects.decimal_odds import DecimalOdds


@dataclass(frozen=True, slots=True)
class OddsQuote:
    """A single odds observation for a selection, quoted by a bookmaker at a
    point in time.

    Carries a full `match` reference so one quote is self-contained - a
    provider adapter can build it from a single response and downstream code
    (persistence, EV comparison) never needs a side-channel match id. This
    closed the long-flagged gap where the entity had no match reference at
    all (Phase 6 decision).
    """

    match: Match
    bookmaker: Bookmaker
    selection: Selection
    odds: DecimalOdds
    quoted_at: datetime

    def __post_init__(self) -> None:
        if self.quoted_at.tzinfo is None:
            raise ValueError("OddsQuote.quoted_at must be timezone-aware (UTC)")
        if self.quoted_at.utcoffset() != timedelta(0):
            raise ValueError("OddsQuote.quoted_at must be expressed in UTC")
