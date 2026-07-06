import pytest

from src.domain.ports.correction_factor_repository import CorrectionFactorRepository
from src.domain.ports.local_odds_provider import LocalOddsProvider
from src.domain.ports.match_repository import MatchRepository
from src.domain.ports.odds_repository import OddsRepository
from src.domain.ports.player_repository import PlayerRepository
from src.domain.ports.player_stats_provider import PlayerStatsProvider
from src.domain.ports.player_stats_repository import PlayerStatsRepository
from src.domain.ports.settled_bet_repository import SettledBetRepository
from src.domain.ports.sharp_odds_provider import SharpOddsProvider
from src.domain.ports.stats_provider import StatsProvider
from src.domain.ports.value_bet_repository import ValueBetRepository

PORTS = [
    MatchRepository,
    OddsRepository,
    ValueBetRepository,
    SharpOddsProvider,
    LocalOddsProvider,
    StatsProvider,
    PlayerStatsProvider,
    PlayerRepository,
    PlayerStatsRepository,
    SettledBetRepository,
    CorrectionFactorRepository,
]


@pytest.mark.parametrize("port", PORTS)
def test_port_cannot_be_instantiated_directly(port: type) -> None:
    with pytest.raises(TypeError):
        port()
