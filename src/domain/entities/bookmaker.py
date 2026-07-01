from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Bookmaker:
    """A bookmaker/sportsbook. `is_sharp` marks a low-margin, sharp reference book."""

    name: str
    is_sharp: bool
    region: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Bookmaker.name must not be empty")
        if not self.region:
            raise ValueError("Bookmaker.region must not be empty")
