"""High-level adapter implementing the domain's StatsProvider port on top of
The Odds API's /scores endpoint - the only historical-results data this
provider offers (there is no dedicated "team form" endpoint).
"""

from src.domain.entities.team import Team
from src.domain.entities.team_form import TeamForm
from src.domain.ports.stats_provider import StatsProvider
from src.infrastructure.providers.api.client import TheOddsApiClient
from src.infrastructure.providers.api.mappers import team_form_from_score_events


class TheOddsApiStatsProvider(StatsProvider):
    def __init__(self, client: TheOddsApiClient, sport_key: str, *, days_from: int = 3) -> None:
        self._client = client
        self._sport_key = sport_key
        self._days_from = days_from

    async def get_team_form(self, team: Team) -> TeamForm:
        events = await self._client.list_scores(self._sport_key, days_from=self._days_from)
        return team_form_from_score_events(team, events)

    async def get_team_forms(self, teams: list[Team]) -> dict[str, TeamForm]:
        """Batch variant beyond the StatsProvider port: one /scores call
        covers every team, avoiding a redundant re-fetch of the same payload
        per team when a use case needs form for a whole slate of matches."""
        events = await self._client.list_scores(self._sport_key, days_from=self._days_from)
        return {team.id: team_form_from_score_events(team, events) for team in teams}
