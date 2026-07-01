from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from src.infrastructure.providers.api.player_stats.dtos import (
    FixtureLineupDTO,
    InjuryEntryDTO,
    PlayerFixtureStatsDTO,
)

_PLAYER_FIXTURE_STATS_LIST_ADAPTER = TypeAdapter(list[PlayerFixtureStatsDTO])
_INJURY_ENTRY_LIST_ADAPTER = TypeAdapter(list[InjuryEntryDTO])


def test_player_fixture_stats_dto_parses_a_realistic_list_payload(
    player_recent_matches_json: dict[str, Any],
) -> None:
    entries = _PLAYER_FIXTURE_STATS_LIST_ADAPTER.validate_python(player_recent_matches_json["data"])

    assert len(entries) == 3
    first = entries[0]
    assert first.fixture.id == "fx-2001"
    assert first.fixture.home_team_name == "Manchester City"
    assert first.player.id == "1100"
    assert first.player.name == "Erling Haaland"
    assert first.minutes_played == 90
    assert first.started is True
    assert first.goals == 2
    assert first.corners_won == 1
    assert entries[2].corners_won is None


def test_player_fixture_stats_dto_defaults_numeric_fields_to_zero() -> None:
    dto = PlayerFixtureStatsDTO.model_validate(
        {
            "fixture": {
                "id": "fx-x",
                "starting_at": "2026-08-15T20:00:00Z",
                "league_id": "soccer_epl",
                "home_team_id": "1",
                "home_team_name": "A",
                "away_team_id": "2",
                "away_team_name": "B",
            },
            "player": {"id": "p1", "name": "Someone", "team_id": "1", "team_name": "A"},
            "minutes_played": 0,
            "started": False,
        }
    )

    assert dto.shots_total == 0
    assert dto.shots_on_target == 0
    assert dto.goals == 0
    assert dto.assists == 0
    assert dto.yellow_cards == 0
    assert dto.red_cards == 0
    assert dto.corners_won is None


@pytest.mark.parametrize(
    "payload",
    [
        {"player": {"id": "p1", "name": "X", "team_id": "1", "team_name": "A"}, "minutes_played": 0, "started": False},
        {
            "fixture": {
                "id": "fx-x",
                "starting_at": "2026-08-15T20:00:00Z",
                "league_id": "soccer_epl",
                "home_team_id": "1",
                "home_team_name": "A",
                "away_team_id": "2",
                "away_team_name": "B",
            },
            "minutes_played": 0,
            "started": False,
        },
    ],
    ids=["missing_fixture", "missing_player"],
)
def test_player_fixture_stats_dto_rejects_malformed_payloads(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PlayerFixtureStatsDTO.model_validate(payload)


def test_injury_entry_dto_parses_a_realistic_list_payload(injuries_json: dict[str, Any]) -> None:
    entries = _INJURY_ENTRY_LIST_ADAPTER.validate_python(injuries_json["data"])

    assert len(entries) == 3
    assert entries[0].status == "Doubtful"
    assert entries[2].status == "Personal Reasons"


def test_injury_entry_dto_position_is_optional() -> None:
    entry = InjuryEntryDTO.model_validate(
        {
            "player_id": "p1",
            "player_name": "Someone",
            "team_id": "1",
            "team_name": "A",
            "status": "Injured",
            "source": "Sportmonks",
            "updated_at": "2026-08-14T09:00:00Z",
        }
    )

    assert entry.position is None


def test_fixture_lineup_dto_parses_confirmed_payload(lineup_confirmed_json: dict[str, Any]) -> None:
    dto = FixtureLineupDTO.model_validate(lineup_confirmed_json["data"])

    assert dto.is_confirmed is True
    assert len(dto.entries) == 2
    assert dto.entries[0].is_starting is True
    assert dto.entries[1].is_starting is False


def test_fixture_lineup_dto_parses_unconfirmed_payload(lineup_unconfirmed_json: dict[str, Any]) -> None:
    dto = FixtureLineupDTO.model_validate(lineup_unconfirmed_json["data"])

    assert dto.is_confirmed is False
    assert len(dto.entries) == 1


def test_fixture_lineup_dto_defaults_entries_to_empty_list() -> None:
    dto = FixtureLineupDTO.model_validate(
        {
            "fixture": {
                "id": "fx-x",
                "starting_at": "2026-08-15T20:00:00Z",
                "league_id": "soccer_epl",
                "home_team_id": "1",
                "home_team_name": "A",
                "away_team_id": "2",
                "away_team_name": "B",
            },
            "is_confirmed": False,
        }
    )

    assert dto.entries == []
