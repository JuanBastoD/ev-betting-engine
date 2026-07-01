from dataclasses import dataclass

from src.domain.entities.match import Match
from src.domain.entities.player import Player
from src.domain.value_objects.probability import Probability


@dataclass(frozen=True, slots=True)
class LineupConfirmation:
    """Whether a player is expected to start a match.

    `is_confirmed` is the flag statistical engines use to adjust confidence
    when the lineup is only an estimate rather than an official
    announcement (typical until ~1h before kickoff). `is_starting` is always
    derived from `start_probability` (>= 0.5), so the two can never
    disagree - when confirmed, `start_probability` must itself be 0.0 or
    1.0 (it's ground truth, not an estimate).
    """

    player: Player
    match: Match
    is_starting: bool
    is_confirmed: bool
    start_probability: Probability

    def __post_init__(self) -> None:
        expected_is_starting = self.start_probability.value >= 0.5
        if self.is_starting != expected_is_starting:
            raise ValueError(
                "LineupConfirmation.is_starting must match "
                "(start_probability.value >= 0.5)"
            )
        if self.is_confirmed and self.start_probability.value not in (0.0, 1.0):
            raise ValueError(
                "LineupConfirmation.start_probability must be 0.0 or 1.0 "
                "when is_confirmed is True"
            )
