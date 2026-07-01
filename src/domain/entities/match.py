from dataclasses import dataclass
from datetime import datetime, timedelta

from src.domain.entities.league import League
from src.domain.entities.team import Team


@dataclass(frozen=True, slots=True)
class Match:
    """A pre-match fixture between two teams. Identity is defined by `id`."""

    id: str
    home_team: Team
    away_team: Team
    league: League
    kickoff_utc: datetime

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Match.id must not be empty")
        if self.home_team.id == self.away_team.id:
            raise ValueError("Match.home_team and Match.away_team must be different teams")
        if self.kickoff_utc.tzinfo is None:
            raise ValueError("Match.kickoff_utc must be timezone-aware (UTC)")
        if self.kickoff_utc.utcoffset() != timedelta(0):
            raise ValueError("Match.kickoff_utc must be expressed in UTC")
