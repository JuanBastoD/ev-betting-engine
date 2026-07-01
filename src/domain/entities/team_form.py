from dataclasses import dataclass

from src.domain.entities.team import Team

_FORM_WINDOW = 10


@dataclass(frozen=True, slots=True)
class TeamForm:
    """Aggregated results/goals for a team over its last 10 matches."""

    team: Team
    matches_played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int

    def __post_init__(self) -> None:
        if not (0 <= self.matches_played <= _FORM_WINDOW):
            raise ValueError(
                f"TeamForm.matches_played must be between 0 and {_FORM_WINDOW}, "
                f"got {self.matches_played}"
            )
        for field_name in ("wins", "draws", "losses", "goals_for", "goals_against"):
            field_value = getattr(self, field_name)
            if field_value < 0:
                raise ValueError(f"TeamForm.{field_name} must not be negative, got {field_value}")
        if self.wins + self.draws + self.losses != self.matches_played:
            raise ValueError(
                "TeamForm.wins + TeamForm.draws + TeamForm.losses must equal "
                "TeamForm.matches_played"
            )
