from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Team:
    """A football team. Identity is defined by `id`."""

    id: str
    name: str
    country: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Team.id must not be empty")
        if not self.name:
            raise ValueError("Team.name must not be empty")
