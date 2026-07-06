from dataclasses import dataclass

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.selection import Selection
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.edge_percentage import EdgePercentage
from src.domain.value_objects.probability import Probability
from src.domain.value_objects.stake import Stake


@dataclass(frozen=True, slots=True)
class ValueBet:
    """A detected positive expected-value betting opportunity.

    `lineup_confirmed` is only meaningful for `model_source=PLAYER_PROPS`
    bets (`PlayerPropDetector`, Phase 8) - whether the underlying lineup
    slot was officially confirmed rather than estimated. `None` for every
    other model source, where the concept doesn't apply; added here
    (optional, defaulting to `None`) rather than living only on the
    transient `PlayerPropDetection` wrapper, since a listing endpoint
    reading persisted `ValueBet`s back out has no other way to recover it.

    `bookmaker` (Phase 10: added once calibration needed to segment
    settled-bet accuracy per bookmaker, closing the second of the "flag,
    don't fix" gaps from Phase 6) is the *local* book this odds observation
    came from - optional and defaulting to `None` for the same
    backward-compatibility reason as `lineup_confirmed`.
    """

    match: Match
    selection: Selection
    local_odds: DecimalOdds
    fair_probability: Probability
    edge: EdgePercentage
    suggested_stake: Stake
    model_source: ModelSource
    lineup_confirmed: bool | None = None
    bookmaker: Bookmaker | None = None

    def __post_init__(self) -> None:
        if self.edge.value <= 0.0:
            raise ValueError(f"ValueBet.edge must be positive, got {self.edge.value}")
