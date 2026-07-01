from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EdgePercentage:
    """Expected-value edge expressed as a percentage.

    A stake is lost in full at worst, so the theoretical floor is -100.0
    (fair probability of winning is 0). There is no theoretical ceiling.
    """

    value: float

    def __post_init__(self) -> None:
        if self.value < -100.0:
            raise ValueError(f"EdgePercentage cannot be less than -100.0, got {self.value}")

    @property
    def is_positive_ev(self) -> bool:
        return self.value > 0.0
