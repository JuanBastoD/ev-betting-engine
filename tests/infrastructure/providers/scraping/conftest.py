from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.domain.entities.league import League
from src.domain.entities.match import Match
from src.domain.entities.team import Team

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture() -> Callable[[str], str]:
    def _load(name: str) -> str:
        return (FIXTURES_DIR / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture
def match() -> Match:
    return Match(
        id="match-col-1",
        home_team=Team(id="junior-fc", name="Junior FC", country="Colombia"),
        away_team=Team(id="america-de-cali", name="America de Cali", country="Colombia"),
        league=League(id="liga-betplay", name="Liga BetPlay Dimayor", country="Colombia"),
        kickoff_utc=datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc),
    )
