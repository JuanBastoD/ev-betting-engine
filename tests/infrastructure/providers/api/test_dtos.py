from datetime import timezone
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from src.infrastructure.providers.api.dtos import EventOddsDTO, ScoreEventDTO


def test_event_odds_dto_parses_a_realistic_list_payload(
    event_odds_list_json: list[dict[str, Any]],
) -> None:
    events = TypeAdapter(list[EventOddsDTO]).validate_python(event_odds_list_json)

    assert len(events) == 2
    first = events[0]
    assert first.id == "e912304de1234567890abcdef123456"
    assert first.home_team == "Manchester United"
    assert first.away_team == "Liverpool"
    assert first.commence_time.tzinfo is not None
    assert first.commence_time.astimezone(timezone.utc).hour == 20
    assert [bookmaker.key for bookmaker in first.bookmakers] == ["pinnacle", "bet365"]

    pinnacle = first.bookmakers[0]
    assert pinnacle.title == "Pinnacle"
    h2h = pinnacle.markets[0]
    assert h2h.key == "h2h"
    assert {outcome.name: outcome.price for outcome in h2h.outcomes} == {
        "Manchester United": 2.10,
        "Liverpool": 3.40,
        "Draw": 3.25,
    }


def test_event_odds_dto_parses_a_single_event_object(
    single_event_odds_json: dict[str, Any],
) -> None:
    event = EventOddsDTO.model_validate(single_event_odds_json)

    assert event.id == "e912304de1234567890abcdef123456"
    assert len(event.bookmakers) == 1
    assert event.bookmakers[0].key == "pinnacle"


def test_event_odds_dto_defaults_missing_bookmakers_to_empty_list() -> None:
    event = EventOddsDTO.model_validate(
        {
            "id": "no-odds-yet",
            "sport_key": "soccer_epl",
            "commence_time": "2026-08-20T12:00:00Z",
            "home_team": "Fulham",
            "away_team": "Brentford",
        }
    )

    assert event.bookmakers == []


def test_event_odds_dto_ignores_unknown_extra_fields() -> None:
    event = EventOddsDTO.model_validate(
        {
            "id": "extra-fields",
            "sport_key": "soccer_epl",
            "commence_time": "2026-08-20T12:00:00Z",
            "home_team": "Fulham",
            "away_team": "Brentford",
            "some_new_field_the_api_added": {"nested": True},
        }
    )

    assert event.id == "extra-fields"


@pytest.mark.parametrize(
    "payload",
    [
        {"sport_key": "soccer_epl", "commence_time": "2026-08-20T12:00:00Z", "home_team": "A", "away_team": "B"},
        {"id": "x", "sport_key": "soccer_epl", "home_team": "A", "away_team": "B"},
        {"id": "x", "sport_key": "soccer_epl", "commence_time": "not-a-date", "home_team": "A", "away_team": "B"},
    ],
    ids=["missing_id", "missing_commence_time", "invalid_commence_time"],
)
def test_event_odds_dto_rejects_malformed_payloads(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        EventOddsDTO.model_validate(payload)


def test_event_odds_dto_list_rejects_a_non_list_top_level_payload() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(list[EventOddsDTO]).validate_python({"not": "a list"})


def test_score_event_dto_parses_a_realistic_list_payload(
    scores_list_json: list[dict[str, Any]],
) -> None:
    events = TypeAdapter(list[ScoreEventDTO]).validate_python(scores_list_json)

    assert len(events) == 6
    completed_with_scores = [e for e in events if e.completed and e.scores is not None]
    assert len(completed_with_scores) == 4

    not_completed = next(e for e in events if not e.completed)
    assert not_completed.scores is None

    completed_but_scoreless = next(e for e in events if e.id == "score-6")
    assert completed_but_scoreless.completed is True
    assert completed_but_scoreless.scores is None


def test_score_event_dto_rejects_missing_completed_field() -> None:
    with pytest.raises(ValidationError):
        ScoreEventDTO.model_validate(
            {
                "id": "x",
                "sport_key": "soccer_epl",
                "commence_time": "2026-08-20T12:00:00Z",
                "home_team": "A",
                "away_team": "B",
            }
        )
