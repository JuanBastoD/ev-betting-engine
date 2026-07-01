import json
from pathlib import Path
from typing import Any

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> Any:
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def player_recent_matches_json() -> dict[str, Any]:
    """Envelope for the player-fixture-stats endpoint: 3 matches for the
    same player (id "1100"), 2 started / 1 not - a 2/3 historical start rate."""
    return _load_fixture("player_recent_matches.json")


@pytest.fixture
def injuries_json() -> dict[str, Any]:
    """Envelope for the injuries endpoint: two entries with statuses that
    map cleanly onto InjuryStatusType, one with an unrecognized status
    string that must be skipped rather than guessed at."""
    return _load_fixture("injuries.json")


@pytest.fixture
def lineup_confirmed_json() -> dict[str, Any]:
    """Envelope for the fixture-lineup endpoint with an official lineup
    already announced."""
    return _load_fixture("lineup_confirmed.json")


@pytest.fixture
def lineup_unconfirmed_json() -> dict[str, Any]:
    """Envelope for the fixture-lineup endpoint before the official lineup
    is announced - `is_confirmed=False`, entries hold a provider "predicted"
    guess. Player "1100" here is the same player as in
    player_recent_matches_json, so tests can chain the two."""
    return _load_fixture("lineup_unconfirmed.json")
