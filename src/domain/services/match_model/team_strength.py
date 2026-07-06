"""Attack/defense strength ratings derived from `TeamForm`.

`TeamForm` (Prompt 3) is an aggregate over up to the last 10 matches with no
per-match dates or venue split baked in, so recency-weighting and the
home/away split both have to be expressed at THIS module's boundary rather
than inside `TeamForm` itself:

- Home/away split: call `calculate_team_strength` once with the team's
  home-only `TeamForm` to get its home rating, and once with its away-only
  `TeamForm` for its away rating - this module doesn't know or care how the
  caller sliced the matches by venue.
- Recency weighting: pass an optional shorter-window `recent_form` (e.g.
  last 5 matches) alongside the full `form` (e.g. last 10); the two
  match-rate windows are blended with `recent_form_weight` favoring the
  shorter one. Omitting `recent_form` still works - it isn't required to
  get a strength rating from "TeamForm, last 10 matches" alone.
"""

from dataclasses import dataclass

from src.domain.entities.team import Team
from src.domain.entities.team_form import TeamForm


@dataclass(frozen=True, slots=True)
class TeamStrength:
    """A team's attack/defense rating, relative to the league average.

    `attack` > 1.0 means the team scores more than the league-average rate;
    `defense` > 1.0 means it concedes more than the league-average rate
    (i.e. a *weaker* defense - this is a "goals conceded" ratio, not a
    defensive-quality score). Zero is allowed (a team held scoreless, or
    conceding nothing, across its whole sample) but not negative.
    """

    team: Team
    attack: float
    defense: float

    def __post_init__(self) -> None:
        if self.attack < 0.0:
            raise ValueError(f"TeamStrength.attack must not be negative, got {self.attack}")
        if self.defense < 0.0:
            raise ValueError(f"TeamStrength.defense must not be negative, got {self.defense}")


def calculate_team_strength(
    *,
    form: TeamForm,
    league_average_goals: float,
    recent_form: TeamForm | None = None,
    recent_form_weight: float = 0.6,
) -> TeamStrength:
    """`league_average_goals` is the league's average goals scored per team
    per match (a single figure suffices: across a full league, total goals
    scored equals total goals conceded, so it doubles as the defensive
    baseline too) - callers compute it once per league and pass it in,
    since deriving it needs every team's form, not just one.

    `recent_form_weight` (applied only when `recent_form` is given) is the
    weight on the shorter/more-recent window; the full `form` window gets
    `1 - recent_form_weight`. Both `form.team` and `recent_form.team` (when
    given) must be the same team - mixing two teams' data is a caller bug.
    """
    if league_average_goals <= 0.0:
        raise ValueError(
            f"league_average_goals must be positive, got {league_average_goals}"
        )
    if form.matches_played == 0:
        raise ValueError("Cannot compute team strength from a TeamForm with 0 matches played")
    if not (0.0 <= recent_form_weight <= 1.0):
        raise ValueError(
            f"recent_form_weight must be within [0.0, 1.0], got {recent_form_weight}"
        )

    goals_for_rate = form.goals_for / form.matches_played
    goals_against_rate = form.goals_against / form.matches_played

    if recent_form is not None:
        if recent_form.team.id != form.team.id:
            raise ValueError(
                "form and recent_form must belong to the same team, got "
                f"{form.team.id!r} and {recent_form.team.id!r}"
            )
        if recent_form.matches_played == 0:
            raise ValueError(
                "Cannot blend a recent_form with 0 matches played"
            )
        recent_goals_for_rate = recent_form.goals_for / recent_form.matches_played
        recent_goals_against_rate = recent_form.goals_against / recent_form.matches_played
        goals_for_rate = (
            recent_form_weight * recent_goals_for_rate
            + (1.0 - recent_form_weight) * goals_for_rate
        )
        goals_against_rate = (
            recent_form_weight * recent_goals_against_rate
            + (1.0 - recent_form_weight) * goals_against_rate
        )

    return TeamStrength(
        team=form.team,
        attack=goals_for_rate / league_average_goals,
        defense=goals_against_rate / league_average_goals,
    )
