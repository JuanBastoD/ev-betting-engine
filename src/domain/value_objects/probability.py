from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Probability:
    """A probability expressed as a fraction in the closed interval [0.0, 1.0]."""

    value: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.value <= 1.0):
            raise ValueError(f"Probability must be within [0.0, 1.0], got {self.value}")
