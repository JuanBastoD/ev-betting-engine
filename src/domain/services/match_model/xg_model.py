"""Dixon-Coles expected-goals model: turns two teams' attack/defense
strengths into a full scoreline probability matrix, and derives 1X2,
Over/Under and BTTS probabilities from it.

Strategy pattern (`MatchStatisticalModel`): `MatchValueDetector` is handed a
model instance and never branches on which one is in use, mirroring
`DevigStrategy` in the market model - the extension point for a future
trained model is `MatchStatisticalModel.predict_match_probabilities`.
"""

import math
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.domain.services.match_model.team_strength import TeamStrength
from src.domain.value_objects.probability import Probability

_DEFAULT_OVER_UNDER_LINES = (1.5, 2.5, 3.5)
_DEFAULT_MAX_GOALS = 10


@dataclass(frozen=True, slots=True)
class OverUnderProbability:
    """`over`/`under` for one goals line (e.g. 2.5), summing to 1.0."""

    line: float
    over: Probability
    under: Probability

    def __post_init__(self) -> None:
        if self.line <= 0.0:
            raise ValueError(f"OverUnderProbability.line must be positive, got {self.line}")


@dataclass(frozen=True, slots=True)
class MatchProbabilities:
    """A statistical model's full opinion on one match: 1X2, Over/Under for
    every configured line, BTTS, and the underlying scoreline matrix
    (`(home_goals, away_goals) -> probability`) they were all derived from -
    kept around for callers that want a specific correct-score probability,
    not just the derived markets.
    """

    home_win: Probability
    draw: Probability
    away_win: Probability
    over_under: tuple[OverUnderProbability, ...]
    btts_yes: Probability
    btts_no: Probability
    score_matrix: Mapping[tuple[int, int], float]

    def over_under_for_line(self, line: float) -> OverUnderProbability:
        for entry in self.over_under:
            if entry.line == line:
                return entry
        raise ValueError(f"No Over/Under probability computed for line {line}")


class MatchStatisticalModel(ABC):
    """One way of turning team strengths into match probabilities. Stateless
    given its configuration (home advantage, correction parameters, ...)."""

    @abstractmethod
    def predict_match_probabilities(
        self,
        home_strength: TeamStrength,
        away_strength: TeamStrength,
        *,
        league_average_goals: float,
    ) -> MatchProbabilities: ...


class DixonColesModel(MatchStatisticalModel):
    """Bivariate-Poisson-with-low-score-correction model (Dixon & Coles,
    1997, "Modelling Association Football Scores and Inefficiencies in the
    Football Betting Market").

    Expected goals: lambda_home = league_average_goals * home_strength.attack
    * away_strength.defense * home_advantage; lambda_away = league_average_goals
    * away_strength.attack * home_strength.defense (no advantage factor - it
    only applies to the home side).

    Plain independent Poisson(lambda_home) x Poisson(lambda_away) understates
    how often low-scoring games (0-0, 1-0, 0-1, 1-1) actually occur, since
    goals aren't quite independent at the low end. Dixon-Coles' tau
    correction reweights exactly those four scorelines:

        tau(x, y) = 1 - lambda_home*lambda_away*rho   if x=0, y=0
                    1 + lambda_home*rho                if x=0, y=1
                    1 + lambda_away*rho                if x=1, y=0
                    1 - rho                             if x=1, y=1
                    1                                    otherwise

    `rho` is a small fitted correlation parameter (paper's estimate for
    English football was about -0.13); it's a plain constructor argument
    here rather than something this pure domain service could fit itself -
    fitting rho from historical results is a future application-layer/
    calibration concern.

    The scoreline grid is truncated to `max_goals` per side (goals beyond
    that are astronomically unlikely for any realistic football lambda) and
    renormalized to sum to exactly 1.0, so every derived probability
    (1X2, Over/Under, BTTS) is internally consistent by construction.

    Known limitation of the tau correction itself (not this implementation):
    each branch is `1 + lambda*rho` (or `1 - rho`), which goes negative once
    `lambda * abs(rho)` exceeds 1 - an unrealistic combination for football
    (lambda over ~10) but reachable by multiplying together individually
    "reasonable" attack/defense/home_advantage/league_average_goals values.
    Found by the hypothesis property test below; each grid cell is floored
    at 0.0 before renormalizing rather than letting one low-mass, out-of-range
    cell turn negative and poison the whole matrix.
    """

    def __init__(
        self,
        *,
        home_advantage: float = 1.35,
        rho: float = -0.1,
        over_under_lines: Sequence[float] = _DEFAULT_OVER_UNDER_LINES,
        max_goals: int = _DEFAULT_MAX_GOALS,
    ) -> None:
        if home_advantage <= 0.0:
            raise ValueError(f"home_advantage must be positive, got {home_advantage}")
        if max_goals < 1:
            raise ValueError(f"max_goals must be at least 1, got {max_goals}")
        self._home_advantage = home_advantage
        self._rho = rho
        self._over_under_lines = tuple(over_under_lines)
        self._max_goals = max_goals

    def predict_match_probabilities(
        self,
        home_strength: TeamStrength,
        away_strength: TeamStrength,
        *,
        league_average_goals: float,
    ) -> MatchProbabilities:
        if league_average_goals <= 0.0:
            raise ValueError(
                f"league_average_goals must be positive, got {league_average_goals}"
            )

        lambda_home = (
            league_average_goals
            * home_strength.attack
            * away_strength.defense
            * self._home_advantage
        )
        lambda_away = league_average_goals * away_strength.attack * home_strength.defense

        matrix = self._score_matrix(lambda_home, lambda_away)

        home_win = sum(p for (x, y), p in matrix.items() if x > y)
        draw = sum(p for (x, y), p in matrix.items() if x == y)
        away_win = sum(p for (x, y), p in matrix.items() if x < y)
        btts_yes = sum(p for (x, y), p in matrix.items() if x >= 1 and y >= 1)

        return MatchProbabilities(
            home_win=Probability(_clamp_unit(home_win)),
            draw=Probability(_clamp_unit(draw)),
            away_win=Probability(_clamp_unit(away_win)),
            over_under=tuple(
                self._over_under_probability(matrix, line) for line in self._over_under_lines
            ),
            btts_yes=Probability(_clamp_unit(btts_yes)),
            btts_no=Probability(_clamp_unit(1.0 - btts_yes)),
            score_matrix=matrix,
        )

    def _score_matrix(
        self, lambda_home: float, lambda_away: float
    ) -> dict[tuple[int, int], float]:
        raw: dict[tuple[int, int], float] = {}
        for x in range(self._max_goals + 1):
            poisson_x = _poisson_pmf(x, lambda_home)
            for y in range(self._max_goals + 1):
                tau = self._tau(x, y, lambda_home, lambda_away)
                # tau's correction terms are 1 + lambda*rho: for a large
                # enough lambda*|rho| (an unrealistic combination for
                # football, but not one this pure function can rule out by
                # construction), that goes negative, which would make this
                # cell a negative "probability". Floor it at zero rather
                # than let a single low-mass cell poison the whole matrix.
                raw[(x, y)] = max(tau * poisson_x * _poisson_pmf(y, lambda_away), 0.0)

        total = sum(raw.values())
        if total <= 0.0:
            raise ValueError(
                "The scoreline grid underflowed to zero probability - "
                f"lambda_home={lambda_home}, lambda_away={lambda_away} are too extreme "
                f"for max_goals={self._max_goals} (check attack/defense/league_average_goals)"
            )
        return {key: value / total for key, value in raw.items()}

    def _tau(self, x: int, y: int, lambda_home: float, lambda_away: float) -> float:
        rho = self._rho
        if x == 0 and y == 0:
            return 1.0 - lambda_home * lambda_away * rho
        if x == 0 and y == 1:
            return 1.0 + lambda_home * rho
        if x == 1 and y == 0:
            return 1.0 + lambda_away * rho
        if x == 1 and y == 1:
            return 1.0 - rho
        return 1.0

    @staticmethod
    def _over_under_probability(
        matrix: Mapping[tuple[int, int], float], line: float
    ) -> OverUnderProbability:
        over = sum(p for (x, y), p in matrix.items() if (x + y) > line)
        return OverUnderProbability(
            line=line, over=Probability(_clamp_unit(over)), under=Probability(_clamp_unit(1.0 - over))
        )


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)


def _clamp_unit(value: float) -> float:
    """Summing ~100 floating-point grid cells can overshoot [0.0, 1.0] by a
    sub-epsilon amount; clamp rather than let that spuriously fail
    Probability's invariant."""
    return min(max(value, 0.0), 1.0)
