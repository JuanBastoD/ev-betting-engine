from abc import ABC, abstractmethod

from src.domain.entities.team import Team
from src.domain.entities.team_form import TeamForm


class StatsProvider(ABC):
    """Gateway to recent-form statistics for a team."""

    @abstractmethod
    async def get_team_form(self, team: Team) -> TeamForm: ...
