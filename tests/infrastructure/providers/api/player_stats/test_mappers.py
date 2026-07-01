from datetime import timedelta, timezone
from typing import Any

import pytest
from pydantic import TypeAdapter

from src.domain.entities.injury_status_type import InjuryStatusType
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_position import PlayerPosition
from src.domain.value_objects.probability import Probability
from src.infrastructure.providers.api.player_stats.dtos import (
    FixtureLineupDTO,
    InjuryEntryDTO,
    PlayerFixtureStatsDTO,
    PlayerRefDTO,
)
from src.infrastructure.providers.api.player_stats.mappers import (
    estimate_start_probability,
    injury_status_from_entry,
    injury_statuses_from_entries,
    lineup_confirmation_from_entry,
    match_from_fixture_ref,
    player_from_player_ref,
    player_match_stats_from_dto,
)

_PLAYER_FIXTURE_STATS_LIST_ADAPTER = TypeAdapter(list[PlayerFixtureStatsDTO])
_INJURY_ENTRY_LIST_ADAPTER = TypeAdapter(list[InjuryEntryDTO])


def test_match_from_fixture_ref_maps_all_fields(
    player_recent_matches_json: dict[str, Any],
) -> None:
    dto = _PLAYER_FIXTURE_STATS_LIST_ADAPTER.validate_python(player_recent_matches_json["data"])[0]

    match = match_from_fixture_ref(dto.fixture)

    assert match.id == "fx-2001"
    assert match.home_team.id == "50"
    assert match.home_team.name == "Manchester City"
    assert match.away_team.name == "Everton"
    assert match.league.id == "soccer_epl"
    assert match.league.name == "EPL"
    assert match.kickoff_utc.tzinfo is not None
    assert match.kickoff_utc.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    ("raw_position", "expected"),
    [
        ("Forward", PlayerPosition.FORWARD),
        ("forward", PlayerPosition.FORWARD),
        ("FW", PlayerPosition.FORWARD),
        ("Attacker", PlayerPosition.FORWARD),
        ("Goalkeeper", PlayerPosition.GOALKEEPER),
        ("Defender", PlayerPosition.DEFENDER),
        ("Midfielder", PlayerPosition.MIDFIELDER),
        ("Some Unrecognized Role", PlayerPosition.UNKNOWN),
        (None, PlayerPosition.UNKNOWN),
    ],
)
def test_player_from_player_ref_normalizes_position(
    raw_position: str | None, expected: PlayerPosition
) -> None:
    ref = PlayerRefDTO(id="p1", name="Someone", team_id="50", team_name="Manchester City", position=raw_position)

    player = player_from_player_ref(ref)

    assert player.position is expected
    assert player.team.id == "50"
    assert player.team.name == "Manchester City"


def test_player_match_stats_from_dto_maps_all_fields(
    player_recent_matches_json: dict[str, Any],
) -> None:
    dto = _PLAYER_FIXTURE_STATS_LIST_ADAPTER.validate_python(player_recent_matches_json["data"])[0]

    stats = player_match_stats_from_dto(dto)

    assert stats.match.id == "fx-2001"
    assert stats.player.id == "1100"
    assert stats.player.name == "Erling Haaland"
    assert stats.minutes_played == 90
    assert stats.started is True
    assert stats.goals == 2
    assert stats.corners_won == 1


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        ("FIT", InjuryStatusType.FIT),
        ("fit", InjuryStatusType.FIT),
        ("Doubtful", InjuryStatusType.DOUBTFUL),
        ("questionable", InjuryStatusType.DOUBTFUL),
        ("Injured", InjuryStatusType.INJURED),
        ("out", InjuryStatusType.INJURED),
        ("Suspended", InjuryStatusType.SUSPENDED),
    ],
)
def test_injury_status_from_entry_normalizes_recognized_statuses(
    raw_status: str, expected: InjuryStatusType
) -> None:
    entry = InjuryEntryDTO(
        player_id="p1",
        player_name="Someone",
        team_id="50",
        team_name="Manchester City",
        status=raw_status,
        source="Sportmonks",
        updated_at="2026-08-14T09:00:00Z",  # type: ignore[arg-type]
    )

    injury_status = injury_status_from_entry(entry)

    assert injury_status is not None
    assert injury_status.status is expected
    assert injury_status.updated_at.tzinfo is not None


def test_injury_status_from_entry_returns_none_for_an_unrecognized_status() -> None:
    entry = InjuryEntryDTO(
        player_id="p1",
        player_name="Someone",
        team_id="50",
        team_name="Manchester City",
        status="Personal Reasons",
        source="Sportmonks",
        updated_at="2026-08-14T09:00:00Z",  # type: ignore[arg-type]
    )

    assert injury_status_from_entry(entry) is None


def test_injury_statuses_from_entries_drops_unrecognized_statuses(
    injuries_json: dict[str, Any],
) -> None:
    entries = _INJURY_ENTRY_LIST_ADAPTER.validate_python(injuries_json["data"])

    statuses = injury_statuses_from_entries(entries)

    assert len(statuses) == 2
    assert {status.player.name for status in statuses} == {"Kevin De Bruyne", "John Stones"}


def _stats_with_started(started: bool) -> PlayerMatchStats:
    from datetime import datetime

    from src.domain.entities.league import League
    from src.domain.entities.match import Match
    from src.domain.entities.player import Player
    from src.domain.entities.team import Team

    team = Team(id="50", name="Manchester City")
    return PlayerMatchStats(
        match=Match(
            id="fx-x",
            home_team=team,
            away_team=Team(id="40", name="Everton"),
            league=League(id="soccer_epl", name="EPL"),
            kickoff_utc=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ),
        player=Player(id="1100", name="Erling Haaland", team=team, position=PlayerPosition.FORWARD),
        minutes_played=90 if started else 0,
        started=started,
        shots_total=0,
        shots_on_target=0,
        goals=0,
        assists=0,
        yellow_cards=0,
        red_cards=0,
    )


def test_estimate_start_probability_computes_historical_start_rate() -> None:
    matches = [_stats_with_started(True), _stats_with_started(True), _stats_with_started(False)]

    probability = estimate_start_probability(matches)

    assert probability.value == pytest.approx(2 / 3)


def test_estimate_start_probability_defaults_to_half_with_no_history() -> None:
    assert estimate_start_probability([]).value == 0.5


def test_estimate_start_probability_handles_all_started_and_none_started() -> None:
    assert estimate_start_probability([_stats_with_started(True)]).value == 1.0
    assert estimate_start_probability([_stats_with_started(False)]).value == 0.0


def test_lineup_confirmation_from_entry_confirmed_starting(
    lineup_confirmed_json: dict[str, Any],
) -> None:
    dto = FixtureLineupDTO.model_validate(lineup_confirmed_json["data"])
    match = match_from_fixture_ref(dto.fixture)
    starting_entry = dto.entries[0]

    confirmation = lineup_confirmation_from_entry(
        starting_entry, match, is_confirmed=True, start_probability=Probability(1.0)
    )

    assert confirmation.is_confirmed is True
    assert confirmation.is_starting is True
    assert confirmation.start_probability.value == 1.0


def test_lineup_confirmation_from_entry_confirmed_not_starting(
    lineup_confirmed_json: dict[str, Any],
) -> None:
    dto = FixtureLineupDTO.model_validate(lineup_confirmed_json["data"])
    match = match_from_fixture_ref(dto.fixture)
    bench_entry = dto.entries[1]

    confirmation = lineup_confirmation_from_entry(
        bench_entry, match, is_confirmed=True, start_probability=Probability(0.0)
    )

    assert confirmation.is_starting is False


def test_lineup_confirmation_from_entry_unconfirmed_uses_estimated_probability(
    lineup_unconfirmed_json: dict[str, Any],
) -> None:
    dto = FixtureLineupDTO.model_validate(lineup_unconfirmed_json["data"])
    match = match_from_fixture_ref(dto.fixture)
    entry = dto.entries[0]

    confirmation = lineup_confirmation_from_entry(
        entry, match, is_confirmed=False, start_probability=Probability(0.667)
    )

    assert confirmation.is_confirmed is False
    assert confirmation.is_starting is True
    assert confirmation.start_probability.value == 0.667
