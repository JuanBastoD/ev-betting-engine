from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class League:
    """A football competition/league. Identity is defined by `id`."""

    id: str
    name: str
    country: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("League.id must not be empty")
        if not self.name:
            raise ValueError("League.name must not be empty")
