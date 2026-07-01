from dataclasses import dataclass
from datetime import datetime, timedelta

from src.domain.entities.injury_status_type import InjuryStatusType
from src.domain.entities.player import Player


@dataclass(frozen=True, slots=True)
class InjuryStatus:
    """A player's fitness report as of `updated_at`, per `source`.

    No match reference: availability is a property of the player, reported
    at a point in time, not scoped to one fixture (same convention as
    TeamForm).
    """

    player: Player
    status: InjuryStatusType
    source: str
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("InjuryStatus.source must not be empty")
        if self.updated_at.tzinfo is None:
            raise ValueError("InjuryStatus.updated_at must be timezone-aware (UTC)")
        if self.updated_at.utcoffset() != timedelta(0):
            raise ValueError("InjuryStatus.updated_at must be expressed in UTC")
