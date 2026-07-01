from dataclasses import dataclass

from src.domain.entities.player_position import PlayerPosition
from src.domain.entities.team import Team


@dataclass(frozen=True, slots=True)
class Player:
    """A football player. Identity is defined by `id`."""

    id: str
    name: str
    team: Team
    position: PlayerPosition

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Player.id must not be empty")
        if not self.name:
            raise ValueError("Player.name must not be empty")
