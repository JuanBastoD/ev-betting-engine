from datetime import datetime, timezone

import pytest

from src.domain.entities.league import League
from src.domain.entities.team import Team


@pytest.fixture
def home_team() -> Team:
    return Team(id="team-home", name="River Plate", country="Argentina")


@pytest.fixture
def away_team() -> Team:
    return Team(id="team-away", name="Boca Juniors", country="Argentina")


@pytest.fixture
def league() -> League:
    return League(id="league-1", name="Liga Profesional", country="Argentina")


@pytest.fixture
def kickoff_utc() -> datetime:
    return datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc)
