"""Adjusts a team's attack strength for key-player absences.

Scoped deliberately narrow: this only touches attack strength (a missing
striker/creative midfielder reduces goal output), not defense - a missing
defender's impact on defensive strength is a different, unmodeled effect
left for a future iteration.

`InjuryStatusType.DOUBTFUL` (an unconfirmed absence) gets a discounted
reduction rather than the full one, and sets `has_unconfirmed_absences` on
the result - mirroring `estimate_start_probability`'s pattern (Prompt 4) of
falling back to a softer estimate rather than asserting certainty the data
doesn't support. Propagating that flag into a persisted `ValueBet` (e.g. to
require human review, or skip auto-betting) is an application-layer
decision beyond this domain service's scope.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.entities.injury_status import InjuryStatus
from src.domain.entities.injury_status_type import InjuryStatusType
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_position import PlayerPosition

DEFAULT_KEY_POSITIONS: frozenset[PlayerPosition] = frozenset(
    {PlayerPosition.FORWARD, PlayerPosition.MIDFIELDER}
)

_RELEVANT_STATUSES = frozenset(
    {InjuryStatusType.INJURED, InjuryStatusType.SUSPENDED, InjuryStatusType.DOUBTFUL}
)


@dataclass(frozen=True, slots=True)
class AbsenceAdjustment:
    """`adjusted_attack` is `attack_strength` after applying every
    significant absence's reduction (multiplicative, so absences compound)."""

    adjusted_attack: float
    has_unconfirmed_absences: bool


def apply_absence_adjustment(
    attack_strength: float,
    *,
    injury_statuses: Sequence[InjuryStatus],
    squad_recent_stats: Sequence[PlayerMatchStats],
    key_positions: frozenset[PlayerPosition] = DEFAULT_KEY_POSITIONS,
    min_goal_involvements: int = 3,
    reduction_per_key_absence: float = 0.15,
    doubtful_weight: float = 0.5,
) -> AbsenceAdjustment:
    """A player counts as a "significant absence" when all three hold:
    their `InjuryStatus.status` is INJURED/SUSPENDED/DOUBTFUL, their
    position is in `key_positions` (default: forwards/midfielders), and
    their goals+assists across `squad_recent_stats` reach
    `min_goal_involvements`. Players with no matching stats (0 involvements)
    or a FIT status never count.

    Each confirmed (INJURED/SUSPENDED) significant absence multiplies
    attack by `(1 - reduction_per_key_absence)`; each DOUBTFUL one
    multiplies by `(1 - reduction_per_key_absence * doubtful_weight)`
    instead (a partial, uncertainty-scaled reduction) and marks the result
    `has_unconfirmed_absences=True`. Both factors are deliberately plain
    configuration, not fitted from data - documented here, tunable by the
    caller.
    """
    if attack_strength < 0.0:
        raise ValueError(f"attack_strength must not be negative, got {attack_strength}")
    if not (0.0 <= reduction_per_key_absence <= 1.0):
        raise ValueError(
            f"reduction_per_key_absence must be within [0.0, 1.0], got {reduction_per_key_absence}"
        )
    if not (0.0 <= doubtful_weight <= 1.0):
        raise ValueError(f"doubtful_weight must be within [0.0, 1.0], got {doubtful_weight}")

    involvements_by_player_id: dict[str, int] = {}
    for stats in squad_recent_stats:
        involvements_by_player_id[stats.player.id] = (
            involvements_by_player_id.get(stats.player.id, 0) + stats.goals + stats.assists
        )

    adjusted_attack = attack_strength
    has_unconfirmed_absences = False

    for injury in injury_statuses:
        if injury.status not in _RELEVANT_STATUSES:
            continue
        if injury.player.position not in key_positions:
            continue
        if involvements_by_player_id.get(injury.player.id, 0) < min_goal_involvements:
            continue

        if injury.status is InjuryStatusType.DOUBTFUL:
            adjusted_attack *= 1.0 - reduction_per_key_absence * doubtful_weight
            has_unconfirmed_absences = True
        else:
            adjusted_attack *= 1.0 - reduction_per_key_absence

    return AbsenceAdjustment(
        adjusted_attack=adjusted_attack, has_unconfirmed_absences=has_unconfirmed_absences
    )
