"""In-memory fakes for every domain port, shared by application-layer
use-case tests and presentation-layer endpoint tests (via FastAPI
dependency overrides) - no real network, browser, or DB beyond the
in-memory SQLite already used elsewhere in the suite.
"""

from src.domain.entities.injury_status import InjuryStatus
from src.domain.entities.lineup_confirmation import LineupConfirmation
from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.player import Player
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.entities.team import Team
from src.domain.entities.team_form import TeamForm
from src.domain.entities.value_bet import ValueBet
from src.domain.ports.local_odds_provider import LocalOddsProvider
from src.domain.ports.match_repository import MatchRepository
from src.domain.ports.odds_repository import OddsRepository
from src.domain.ports.player_repository import PlayerRepository
from src.domain.ports.player_stats_provider import PlayerStatsProvider
from src.domain.ports.player_stats_repository import PlayerStatsRepository
from src.domain.ports.sharp_odds_provider import SharpOddsProvider
from src.domain.ports.stats_provider import StatsProvider
from src.domain.ports.value_bet_repository import ValueBetRepository


class FakeMatchRepository(MatchRepository):
    def __init__(self, matches: list[Match] | None = None) -> None:
        self._by_id: dict[str, Match] = {m.id: m for m in (matches or [])}

    async def get_by_id(self, match_id: str) -> Match | None:
        return self._by_id.get(match_id)

    async def list_upcoming(self) -> list[Match]:
        return list(self._by_id.values())

    async def save(self, match: Match) -> None:
        self._by_id[match.id] = match


class FakeOddsRepository(OddsRepository):
    def __init__(self) -> None:
        self.saved: list[OddsQuote] = []

    async def save(self, odds_quote: OddsQuote) -> None:
        self.saved.append(odds_quote)

    async def list_by_match_id(self, match_id: str) -> list[OddsQuote]:
        return [q for q in self.saved if q.match.id == match_id]


class FakePlayerRepository(PlayerRepository):
    def __init__(self) -> None:
        self._by_id: dict[str, Player] = {}

    async def get_by_id(self, player_id: str) -> Player | None:
        return self._by_id.get(player_id)

    async def list_by_team_id(self, team_id: str) -> list[Player]:
        return [p for p in self._by_id.values() if p.team.id == team_id]

    async def save(self, player: Player) -> None:
        self._by_id[player.id] = player


class FakePlayerStatsRepository(PlayerStatsRepository):
    def __init__(self) -> None:
        self.saved: list[PlayerMatchStats] = []

    async def save(self, stats: PlayerMatchStats) -> None:
        self.saved.append(stats)

    async def list_by_player_id(self, player_id: str) -> list[PlayerMatchStats]:
        return [s for s in self.saved if s.player.id == player_id]

    async def list_by_match_id(self, match_id: str) -> list[PlayerMatchStats]:
        return [s for s in self.saved if s.match.id == match_id]


class FakeValueBetRepository(ValueBetRepository):
    def __init__(self) -> None:
        self.saved: list[ValueBet] = []

    async def save(self, value_bet: ValueBet) -> None:
        self.saved.append(value_bet)

    async def list_by_match_id(self, match_id: str) -> list[ValueBet]:
        return [vb for vb in self.saved if vb.match.id == match_id]

    async def list_all(self) -> list[ValueBet]:
        return list(self.saved)


class FakeSharpOddsProvider(SharpOddsProvider):
    def __init__(self, quotes_by_match_id: dict[str, list[OddsQuote]] | None = None) -> None:
        self._quotes_by_match_id = quotes_by_match_id or {}

    async def get_odds(self, match: Match) -> list[OddsQuote]:
        return list(self._quotes_by_match_id.get(match.id, []))


class FakeStatsProvider(StatsProvider):
    def __init__(self, forms_by_team_id: dict[str, TeamForm] | None = None) -> None:
        self._forms_by_team_id = forms_by_team_id or {}

    async def get_team_form(self, team: Team) -> TeamForm:
        return self._forms_by_team_id[team.id]


class FakeLocalOddsProvider(LocalOddsProvider):
    def __init__(
        self,
        quotes_by_match_id: dict[str, list[OddsQuote]] | None = None,
        props_by_match_id: dict[str, list[PlayerPropMarket]] | None = None,
    ) -> None:
        self._quotes_by_match_id = quotes_by_match_id or {}
        self._props_by_match_id = props_by_match_id or {}

    async def get_odds(self, match: Match) -> list[OddsQuote]:
        return list(self._quotes_by_match_id.get(match.id, []))

    async def get_player_props(self, match: Match) -> list[PlayerPropMarket]:
        return list(self._props_by_match_id.get(match.id, []))


class FakePlayerStatsProvider(PlayerStatsProvider):
    def __init__(
        self,
        recent_matches_by_player_id: dict[str, list[PlayerMatchStats]] | None = None,
        injuries_by_match_id: dict[str, list[InjuryStatus]] | None = None,
        lineups_by_match_id: dict[str, list[LineupConfirmation]] | None = None,
    ) -> None:
        self._recent_matches_by_player_id = recent_matches_by_player_id or {}
        self._injuries_by_match_id = injuries_by_match_id or {}
        self._lineups_by_match_id = lineups_by_match_id or {}

    async def get_player_recent_matches(self, player_id: str, n: int = 10) -> list[PlayerMatchStats]:
        return list(self._recent_matches_by_player_id.get(player_id, []))[:n]

    async def get_injury_report(self, match_id: str) -> list[InjuryStatus]:
        return list(self._injuries_by_match_id.get(match_id, []))

    async def get_confirmed_lineup(self, match_id: str) -> list[LineupConfirmation]:
        return list(self._lineups_by_match_id.get(match_id, []))
