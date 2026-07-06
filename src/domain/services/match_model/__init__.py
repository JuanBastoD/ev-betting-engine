"""Match-statistics quantitative core: derive a team's own +EV opinion from
team-form goal data (Dixon-Coles xG), independent of the market-model's
Pinnacle devig (Prompt 6).

Pure domain service - no infrastructure, no I/O, fully deterministic.
`MatchValueDetector` reuses `MarketValueDetector` (from
`src.domain.services.market_model`) for the market side of its
double-confirmation policy rather than duplicating devig logic.
"""

from src.domain.services.match_model.absence_adjustment import (
    AbsenceAdjustment,
    apply_absence_adjustment,
)
from src.domain.services.match_model.match_value_detector import (
    ConfirmationMode,
    MatchValueDetector,
)
from src.domain.services.match_model.team_strength import TeamStrength, calculate_team_strength
from src.domain.services.match_model.xg_model import (
    DixonColesModel,
    MatchProbabilities,
    MatchStatisticalModel,
    OverUnderProbability,
)

__all__ = [
    "AbsenceAdjustment",
    "ConfirmationMode",
    "DixonColesModel",
    "MatchProbabilities",
    "MatchStatisticalModel",
    "MatchValueDetector",
    "OverUnderProbability",
    "TeamStrength",
    "apply_absence_adjustment",
    "calculate_team_strength",
]
