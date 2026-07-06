from datetime import datetime, timezone

from src.application.use_cases.ingest_player_stats import IngestPlayerStatsUseCase
from src.domain.entities.injury_status import InjuryStatus
from src.domain.entities.injury_status_type import InjuryStatusType
from src.domain.entities.lineup_confirmation import LineupConfirmation
from src.domain.entities.match import Match
from src.domain.entities.player import Player
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_position import PlayerPosition
from src.domain.entities.team import Team
from src.domain.value_objects.probability import Probability
from tests.fakes import FakePlayerRepository, FakePlayerStatsProvider, FakePlayerStatsRepository

UPDATED_AT = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def _stats(match: Match, player: Player, *, minutes_played: int = 90) -> PlayerMatchStats:
    return PlayerMatchStats(
        match=match, player=player, minutes_played=minutes_played, started=True,
        shots_total=4, shots_on_target=2, goals=0, assists=0, yellow_cards=0, red_cards=0,
    )


async def test_execute_registers_players_from_lineup_and_persists_their_recent_stats(
    match: Match, home_team: Team
) -> None:
    striker = Player(id="p-striker", name="Carlos Bacca", team=home_team, position=PlayerPosition.FORWARD)
    lineup = [
        LineupConfirmation(
            player=striker, match=match, is_starting=True, is_confirmed=True,
            start_probability=Probability(1.0),
        )
    ]
    recent_stats = [_stats(match, striker), _stats(match, striker)]
    provider = FakePlayerStatsProvider(
        recent_matches_by_player_id={striker.id: recent_stats},
        lineups_by_match_id={match.id: lineup},
    )
    player_repository = FakePlayerRepository()
    player_stats_repository = FakePlayerStatsRepository()

    use_case = IngestPlayerStatsUseCase(
        player_stats_provider=provider,
        player_repository=player_repository,
        player_stats_repository=player_stats_repository,
    )
    result = await use_case.execute(match)

    assert result.lineup_confirmations == lineup
    assert result.injury_statuses == []
    assert result.recent_stats_by_player_id[striker.id] == recent_stats
    assert await player_repository.get_by_id(striker.id) == striker
    assert player_stats_repository.saved == recent_stats


async def test_execute_registers_players_from_injury_report_too(match: Match, home_team: Team) -> None:
    keeper = Player(id="p-keeper", name="Kevin Mier", team=home_team, position=PlayerPosition.GOALKEEPER)
    injuries = [InjuryStatus(player=keeper, status=InjuryStatusType.DOUBTFUL, source="test", updated_at=UPDATED_AT)]
    provider = FakePlayerStatsProvider(
        recent_matches_by_player_id={keeper.id: [_stats(match, keeper)]},
        injuries_by_match_id={match.id: injuries},
    )
    player_repository = FakePlayerRepository()
    player_stats_repository = FakePlayerStatsRepository()

    use_case = IngestPlayerStatsUseCase(
        player_stats_provider=provider,
        player_repository=player_repository,
        player_stats_repository=player_stats_repository,
    )
    result = await use_case.execute(match)

    assert result.injury_statuses == injuries
    assert await player_repository.get_by_id(keeper.id) == keeper


async def test_execute_with_no_lineup_or_injury_data_registers_no_players(match: Match) -> None:
    provider = FakePlayerStatsProvider()
    player_repository = FakePlayerRepository()
    player_stats_repository = FakePlayerStatsRepository()

    use_case = IngestPlayerStatsUseCase(
        player_stats_provider=provider,
        player_repository=player_repository,
        player_stats_repository=player_stats_repository,
    )
    result = await use_case.execute(match)

    assert result.lineup_confirmations == []
    assert result.injury_statuses == []
    assert result.recent_stats_by_player_id == {}


async def test_recent_matches_window_is_forwarded_to_the_provider(match: Match, home_team: Team) -> None:
    striker = Player(id="p-striker", name="Carlos Bacca", team=home_team, position=PlayerPosition.FORWARD)
    lineup = [
        LineupConfirmation(
            player=striker, match=match, is_starting=True, is_confirmed=True,
            start_probability=Probability(1.0),
        )
    ]
    many_matches = [_stats(match, striker) for _ in range(10)]
    provider = FakePlayerStatsProvider(
        recent_matches_by_player_id={striker.id: many_matches}, lineups_by_match_id={match.id: lineup}
    )
    use_case = IngestPlayerStatsUseCase(
        player_stats_provider=provider,
        player_repository=FakePlayerRepository(),
        player_stats_repository=FakePlayerStatsRepository(),
        recent_matches_window=3,
    )

    result = await use_case.execute(match)

    assert len(result.recent_stats_by_player_id[striker.id]) == 3
