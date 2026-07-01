from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Stake:
    """A suggested monetary amount to wager. Must be strictly positive."""

    amount: float

    def __post_init__(self) -> None:
        if self.amount <= 0.0:
            raise ValueError(f"Stake amount must be greater than 0, got {self.amount}")
