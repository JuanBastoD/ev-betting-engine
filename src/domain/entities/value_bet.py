from dataclasses import dataclass

from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.selection import Selection
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.edge_percentage import EdgePercentage
from src.domain.value_objects.probability import Probability
from src.domain.value_objects.stake import Stake


@dataclass(frozen=True, slots=True)
class ValueBet:
    """A detected positive expected-value betting opportunity."""

    match: Match
    selection: Selection
    local_odds: DecimalOdds
    fair_probability: Probability
    edge: EdgePercentage
    suggested_stake: Stake
    model_source: ModelSource

    def __post_init__(self) -> None:
        if self.edge.value <= 0.0:
            raise ValueError(f"ValueBet.edge must be positive, got {self.edge.value}")
