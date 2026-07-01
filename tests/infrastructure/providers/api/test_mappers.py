from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import TypeAdapter

from src.domain.entities.market_type import MarketType
from src.domain.entities.team import Team
from src.infrastructure.providers.api.dtos import EventOddsDTO, ScoreEntryDTO, ScoreEventDTO
from src.infrastructure.providers.api.mappers import (
    league_from_sport,
    match_from_event_odds_dto,
    odds_quotes_from_event_odds_dto,
    team_form_from_score_events,
    team_from_name,
)

_EVENT_LIST_ADAPTER = TypeAdapter(list[EventOddsDTO])
_SCORE_LIST_ADAPTER = TypeAdapter(list[ScoreEventDTO])


@pytest.mark.parametrize(
    ("name", "expected_id"),
    [
        ("Manchester United", "manchester-united"),
        ("Wolverhampton Wanderers", "wolverhampton-wanderers"),
        ("Nott'm Forest", "nott-m-forest"),
    ],
)
def test_team_from_name_derives_a_slug_id(name: str, expected_id: str) -> None:
    team = team_from_name(name)

    assert team.id == expected_id
    assert team.name == name
    assert team.country is None


def test_league_from_sport_uses_sport_title_when_present() -> None:
    league = league_from_sport("soccer_epl", "EPL")

    assert league.id == "soccer_epl"
    assert league.name == "EPL"


def test_league_from_sport_falls_back_to_sport_key_when_no_title() -> None:
    league = league_from_sport("soccer_epl", None)

    assert league.name == "soccer_epl"


def test_match_from_event_odds_dto_maps_all_fields(
    single_event_odds_json: dict[str, Any],
) -> None:
    dto = EventOddsDTO.model_validate(single_event_odds_json)

    match = match_from_event_odds_dto(dto)

    assert match.id == "e912304de1234567890abcdef123456"
    assert match.home_team.name == "Manchester United"
    assert match.away_team.name == "Liverpool"
    assert match.league.id == "soccer_epl"
    assert match.league.name == "EPL"
    assert match.kickoff_utc.tzinfo is not None
    assert match.kickoff_utc.utcoffset() == timedelta(0)


def test_odds_quotes_from_event_odds_dto_maps_only_the_sharp_bookmaker(
    event_odds_list_json: list[dict[str, Any]],
) -> None:
    dto = _EVENT_LIST_ADAPTER.validate_python(event_odds_list_json)[0]

    quotes = odds_quotes_from_event_odds_dto(dto, sharp_bookmaker_key="pinnacle")

    assert len(quotes) == 3
    assert all(quote.bookmaker.name == "Pinnacle" for quote in quotes)
    assert all(quote.bookmaker.is_sharp is True for quote in quotes)
    assert all(quote.selection.market_type is MarketType.MATCH_WINNER_1X2 for quote in quotes)

    by_outcome = {quote.selection.outcome: quote.odds.value for quote in quotes}
    assert by_outcome == {"Home": 2.10, "Away": 3.40, "Draw": 3.25}


def test_odds_quotes_from_event_odds_dto_can_target_a_different_bookmaker(
    event_odds_list_json: list[dict[str, Any]],
) -> None:
    dto = _EVENT_LIST_ADAPTER.validate_python(event_odds_list_json)[0]

    quotes = odds_quotes_from_event_odds_dto(dto, sharp_bookmaker_key="bet365")

    assert len(quotes) == 3
    assert all(quote.bookmaker.name == "Bet365" for quote in quotes)
    # Marked is_sharp=True regardless of which bookmaker this adapter is
    # configured to treat as the reference - "sharp" here is a role, not an
    # intrinsic property of a specific bookmaker name.
    assert all(quote.bookmaker.is_sharp is True for quote in quotes)


def test_odds_quotes_from_event_odds_dto_returns_empty_list_when_bookmaker_not_found(
    event_odds_list_json: list[dict[str, Any]],
) -> None:
    dto = _EVENT_LIST_ADAPTER.validate_python(event_odds_list_json)[0]

    quotes = odds_quotes_from_event_odds_dto(dto, sharp_bookmaker_key="williamhill")

    assert quotes == []


def test_odds_quotes_from_event_odds_dto_skips_non_h2h_markets() -> None:
    dto = EventOddsDTO.model_validate(
        {
            "id": "totals-event",
            "sport_key": "soccer_epl",
            "commence_time": "2026-08-15T20:00:00Z",
            "home_team": "Manchester United",
            "away_team": "Liverpool",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "title": "Pinnacle",
                    "markets": [
                        {
                            "key": "totals",
                            "outcomes": [
                                {"name": "Over", "price": 1.90, "point": 2.5},
                                {"name": "Under", "price": 1.95, "point": 2.5},
                            ],
                        }
                    ],
                }
            ],
        }
    )

    quotes = odds_quotes_from_event_odds_dto(dto, sharp_bookmaker_key="pinnacle")

    assert quotes == []


def test_odds_quotes_quoted_at_falls_back_to_now_when_no_last_update_present() -> None:
    dto = EventOddsDTO.model_validate(
        {
            "id": "no-timestamps",
            "sport_key": "soccer_epl",
            "commence_time": "2026-08-15T20:00:00Z",
            "home_team": "Manchester United",
            "away_team": "Liverpool",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "title": "Pinnacle",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [{"name": "Draw", "price": 3.25}],
                        }
                    ],
                }
            ],
        }
    )

    before = datetime.now(timezone.utc)
    quotes = odds_quotes_from_event_odds_dto(dto, sharp_bookmaker_key="pinnacle")
    after = datetime.now(timezone.utc)

    assert len(quotes) == 1
    assert before <= quotes[0].quoted_at <= after


def test_team_form_from_score_events_aggregates_last_completed_matches(
    scores_list_json: list[dict[str, Any]],
) -> None:
    events = _SCORE_LIST_ADAPTER.validate_python(scores_list_json)
    team = Team(id="manchester-united", name="Manchester United")

    form = team_form_from_score_events(team, events)

    assert form.matches_played == 4
    assert form.wins == 2
    assert form.draws == 1
    assert form.losses == 1
    assert form.goals_for == 6
    assert form.goals_against == 4


def test_team_form_from_score_events_returns_zeroed_form_for_a_team_with_no_matches(
    scores_list_json: list[dict[str, Any]],
) -> None:
    events = _SCORE_LIST_ADAPTER.validate_python(scores_list_json)
    team = Team(id="tottenham-hotspur", name="Tottenham Hotspur")

    form = team_form_from_score_events(team, events)

    assert form.matches_played == 0
    assert form.wins == form.draws == form.losses == 0
    assert form.goals_for == form.goals_against == 0


def test_team_form_from_score_events_keeps_only_the_most_recent_ten() -> None:
    team = Team(id="team-x", name="Team X")
    base_time = datetime(2026, 6, 1, tzinfo=timezone.utc)
    events = [
        ScoreEventDTO(
            id=f"match-{i}",
            sport_key="soccer_epl",
            commence_time=base_time - timedelta(days=i),
            completed=True,
            home_team="Team X",
            away_team="Opponent",
            scores=[ScoreEntryDTO(name="Team X", score="1"), ScoreEntryDTO(name="Opponent", score="0")],
        )
        for i in range(12)
    ]

    form = team_form_from_score_events(team, events)

    assert form.matches_played == 10
    assert form.wins == 10
    assert form.goals_for == 10
    assert form.goals_against == 0


def test_team_form_from_score_events_skips_events_with_a_non_numeric_score() -> None:
    team = Team(id="team-x", name="Team X")
    events = [
        ScoreEventDTO(
            id="malformed-score",
            sport_key="soccer_epl",
            commence_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
            completed=True,
            home_team="Team X",
            away_team="Opponent",
            scores=[
                ScoreEntryDTO(name="Team X", score="TBD"),
                ScoreEntryDTO(name="Opponent", score="0"),
            ],
        ),
        ScoreEventDTO(
            id="valid-score",
            sport_key="soccer_epl",
            commence_time=datetime(2026, 5, 25, tzinfo=timezone.utc),
            completed=True,
            home_team="Team X",
            away_team="Opponent",
            scores=[
                ScoreEntryDTO(name="Team X", score="2"),
                ScoreEntryDTO(name="Opponent", score="1"),
            ],
        ),
    ]

    form = team_form_from_score_events(team, events)

    assert form.matches_played == 1
    assert form.wins == 1
    assert form.goals_for == 2
    assert form.goals_against == 1


def test_team_form_from_score_events_skips_events_missing_the_teams_own_score_entry() -> None:
    team = Team(id="team-x", name="Team X")
    events = [
        ScoreEventDTO(
            id="null-score-for-team",
            sport_key="soccer_epl",
            commence_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
            completed=True,
            home_team="Team X",
            away_team="Opponent",
            scores=[
                ScoreEntryDTO(name="Team X", score=None),
                ScoreEntryDTO(name="Opponent", score="0"),
            ],
        )
    ]

    form = team_form_from_score_events(team, events)

    assert form.matches_played == 0
