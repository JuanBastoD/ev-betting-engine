from dataclasses import dataclass
from datetime import datetime, timedelta

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.match import Match
from src.domain.entities.player_prop_type import PlayerPropType
from src.domain.value_objects.decimal_odds import DecimalOdds


@dataclass(frozen=True, slots=True)
class PlayerPropMarket:
    """A single player-prop odds observation quoted by a bookmaker.

    Carries a full `match` reference (unlike `OddsQuote`, whose missing match
    reference is a known gap) so a provider adapter can produce a
    self-contained observation from a single page/response.

    `player_name` is the bookmaker's display name for the player, not a
    `Player` entity: odds sources expose only a label, and resolving it to a
    known `Player` (id, team, position) is a matching concern that belongs to
    a later application-layer step, not to ingestion.

    `line` carries the threshold for Over/Under-style props (e.g. 1.5 for
    "Over 1.5 shots on target") and is None for lineless props such as
    "anytime goalscorer", where `outcome` alone (e.g. "Yes") describes the bet.
    """

    match: Match
    bookmaker: Bookmaker
    player_name: str
    prop_type: PlayerPropType
    outcome: str
    line: float | None
    odds: DecimalOdds
    quoted_at: datetime

    def __post_init__(self) -> None:
        if not self.player_name:
            raise ValueError("PlayerPropMarket.player_name must not be empty")
        if not self.outcome:
            raise ValueError("PlayerPropMarket.outcome must not be empty")
        if self.line is not None and self.line <= 0:
            raise ValueError(f"PlayerPropMarket.line must be positive when set, got {self.line}")
        if self.quoted_at.tzinfo is None:
            raise ValueError("PlayerPropMarket.quoted_at must be timezone-aware (UTC)")
        if self.quoted_at.utcoffset() != timedelta(0):
            raise ValueError("PlayerPropMarket.quoted_at must be expressed in UTC")
