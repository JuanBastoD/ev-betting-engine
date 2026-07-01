import pytest

from src.domain.entities.player import Player
from src.domain.entities.player_position import PlayerPosition
from src.domain.entities.team import Team


@pytest.fixture
def team() -> Team:
    return Team(id="team-1", name="River Plate")


def test_valid_player_construction(team: Team) -> None:
    player = Player(id="player-1", name="Julian Alvarez", team=team, position=PlayerPosition.FORWARD)

    assert player.id == "player-1"
    assert player.name == "Julian Alvarez"
    assert player.team is team
    assert player.position is PlayerPosition.FORWARD


@pytest.mark.parametrize(("id_", "name"), [("", "Julian Alvarez"), ("player-1", "")])
def test_player_requires_non_empty_id_and_name(id_: str, name: str, team: Team) -> None:
    with pytest.raises(ValueError):
        Player(id=id_, name=name, team=team, position=PlayerPosition.FORWARD)
