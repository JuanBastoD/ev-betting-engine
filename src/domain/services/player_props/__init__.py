"""Player-prop quantitative core: a player's own Over/Under probability
from historical per-90 rates (Poisson), independent of the market-model
devig (Prompt 6) and of the match-model xG engine (Prompt 7) - it reuses
only `kelly_stake`/`calculate_ev` from the former and one narrow,
documented field (`TeamStrength.defense`) from the latter, never their
Poisson/devig internals.

Pure domain service - no infrastructure, no I/O, fully deterministic.
"""

from src.domain.services.player_props.player_model import (
    PlayerPropsModel,
    PoissonPropsModel,
    confidence_adjusted_probability,
    confidence_penalty,
    expected_minutes_from_lineup,
    opponent_factor_from_team_strength,
)
from src.domain.services.player_props.player_prop_detector import (
    PlayerPropDetection,
    PlayerPropDetector,
)
from src.domain.services.player_props.prop_ev_calculator import calculate_prop_ev

__all__ = [
    "PlayerPropDetection",
    "PlayerPropDetector",
    "PlayerPropsModel",
    "PoissonPropsModel",
    "calculate_prop_ev",
    "confidence_adjusted_probability",
    "confidence_penalty",
    "expected_minutes_from_lineup",
    "opponent_factor_from_team_strength",
]
