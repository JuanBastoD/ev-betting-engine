from datetime import datetime, timedelta, timezone

import pytest

from src.domain.entities.injury_status import InjuryStatus
from src.domain.entities.injury_status_type import InjuryStatusType
from src.domain.entities.player import Player
from src.domain.entities.player_position import PlayerPosition
from src.domain.entities.team import Team


@pytest.fixture
def player() -> Player:
    return Player(
        id="player-1",
        name="Julian Alvarez",
        team=Team(id="team-1", name="River Plate"),
        position=PlayerPosition.FORWARD,
    )


def test_valid_injury_status_construction(player: Player) -> None:
    updated_at = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)

    injury_status = InjuryStatus(
        player=player, status=InjuryStatusType.DOUBTFUL, source="Sportmonks", updated_at=updated_at
    )

    assert injury_status.player is player
    assert injury_status.status is InjuryStatusType.DOUBTFUL
    assert injury_status.source == "Sportmonks"
    assert injury_status.updated_at == updated_at


def test_injury_status_requires_non_empty_source(player: Player) -> None:
    with pytest.raises(ValueError):
        InjuryStatus(
            player=player,
            status=InjuryStatusType.FIT,
            source="",
            updated_at=datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc),
        )


def test_injury_status_requires_timezone_aware_updated_at(player: Player) -> None:
    with pytest.raises(ValueError):
        InjuryStatus(
            player=player,
            status=InjuryStatusType.FIT,
            source="Sportmonks",
            updated_at=datetime(2026, 8, 14, 10, 0),
        )


def test_injury_status_requires_utc_updated_at(player: Player) -> None:
    with pytest.raises(ValueError):
        InjuryStatus(
            player=player,
            status=InjuryStatusType.FIT,
            source="Sportmonks",
            updated_at=datetime(2026, 8, 14, 10, 0, tzinfo=timezone(timedelta(hours=2))),
        )
