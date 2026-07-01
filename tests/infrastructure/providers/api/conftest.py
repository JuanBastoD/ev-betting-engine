import json
from pathlib import Path
from typing import Any

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> Any:
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def event_odds_list_json() -> list[dict[str, Any]]:
    """Response body of GET /sports/{sport}/odds - two events, one of which
    has both Pinnacle and a non-sharp bookmaker (Bet365)."""
    return _load_fixture("event_odds_list.json")


@pytest.fixture
def single_event_odds_json() -> dict[str, Any]:
    """Response body of GET /sports/{sport}/events/{eventId}/odds - a single
    event object (not wrapped in a list), Pinnacle only."""
    return _load_fixture("single_event_odds.json")


@pytest.fixture
def scores_list_json() -> list[dict[str, Any]]:
    """Response body of GET /sports/{sport}/scores for Manchester United:
    4 completed results (2W/1D/1L), 1 not-yet-completed event, and 1
    completed-but-scoreless event (malformed/incomplete data from the
    provider) - both of the latter two must be excluded from form
    aggregation."""
    return _load_fixture("scores_list.json")
