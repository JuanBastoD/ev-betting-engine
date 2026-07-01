from dataclasses import dataclass
from datetime import datetime, timedelta

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.selection import Selection
from src.domain.value_objects.decimal_odds import DecimalOdds


@dataclass(frozen=True, slots=True)
class OddsQuote:
    """A single odds observation for a selection, quoted by a bookmaker at a point in time."""

    bookmaker: Bookmaker
    selection: Selection
    odds: DecimalOdds
    quoted_at: datetime

    def __post_init__(self) -> None:
        if self.quoted_at.tzinfo is None:
            raise ValueError("OddsQuote.quoted_at must be timezone-aware (UTC)")
        if self.quoted_at.utcoffset() != timedelta(0):
            raise ValueError("OddsQuote.quoted_at must be expressed in UTC")
