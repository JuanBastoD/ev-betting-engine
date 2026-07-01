from dataclasses import dataclass

from src.domain.entities.match import Match
from src.domain.entities.player import Player


@dataclass(frozen=True, slots=True)
class PlayerMatchStats:
    """One player's statistical line for a single match.

    `started` (whether the player was in the starting XI, as opposed to
    coming on as a substitute or not appearing) isn't in the minimal field
    list a stats API is expected to expose, but it's standard data any real
    provider includes, and it's what the lineup-estimation logic in the
    player_stats provider needs to compute a historical start rate.
    """

    match: Match
    player: Player
    minutes_played: int
    started: bool
    shots_total: int
    shots_on_target: int
    goals: int
    assists: int
    yellow_cards: int
    red_cards: int
    corners_won: int | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "minutes_played",
            "shots_total",
            "shots_on_target",
            "goals",
            "assists",
            "yellow_cards",
            "red_cards",
        ):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"PlayerMatchStats.{field_name} must not be negative, got {value}")
        if self.corners_won is not None and self.corners_won < 0:
            raise ValueError(
                f"PlayerMatchStats.corners_won must not be negative, got {self.corners_won}"
            )
        if self.shots_on_target > self.shots_total:
            raise ValueError(
                "PlayerMatchStats.shots_on_target cannot exceed PlayerMatchStats.shots_total"
            )
