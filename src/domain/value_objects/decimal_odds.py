from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DecimalOdds:
    """Odds expressed in decimal (European) format, e.g. 2.10."""

    value: float

    def __post_init__(self) -> None:
        if self.value <= 1.0:
            raise ValueError(f"DecimalOdds must be greater than 1.0, got {self.value}")

    @property
    def implied_probability(self) -> float:
        return 1.0 / self.value
