"""DTO -> domain Entity mapping (Anti-Corruption Layer) for The Odds API.

The domain never sees an EventOddsDTO/ScoreEventDTO - this is the only module
allowed to know both shapes exist.
"""

import re
from collections.abc import Sequence
from datetime import datetime, timezone

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.league import League
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.selection import Selection
from src.domain.entities.team import Team
from src.domain.entities.team_form import TeamForm
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.infrastructure.providers.api.dtos import EventOddsDTO, ScoreEventDTO

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
_FORM_WINDOW = 10


def _slugify(name: str) -> str:
    """The API has no stable team id, only a display name - derive one."""
    slug = _SLUG_PATTERN.sub("-", name.strip().lower()).strip("-")
    return slug or "unknown"


def team_from_name(name: str) -> Team:
    return Team(id=_slugify(name), name=name)


def league_from_sport(sport_key: str, sport_title: str | None) -> League:
    # sport_key (e.g. "soccer_epl") is already a stable slug from the API,
    # so it doubles as League.id with no derivation needed.
    return League(id=sport_key, name=sport_title or sport_key)


def match_from_event_odds_dto(dto: EventOddsDTO) -> Match:
    return Match(
        id=dto.id,
        home_team=team_from_name(dto.home_team),
        away_team=team_from_name(dto.away_team),
        league=league_from_sport(dto.sport_key, dto.sport_title),
        kickoff_utc=dto.commence_time.astimezone(timezone.utc),
    )


def _outcome_label(outcome_name: str, dto: EventOddsDTO) -> str:
    if outcome_name == dto.home_team:
        return "Home"
    if outcome_name == dto.away_team:
        return "Away"
    return "Draw"


def odds_quotes_from_event_odds_dto(
    dto: EventOddsDTO, *, sharp_bookmaker_key: str, region: str = "eu"
) -> list[OddsQuote]:
    """Map one event's bookmakers/markets to OddsQuotes for the 1X2 market,
    keeping only the configured sharp bookmaker and marking it is_sharp=True.

    Non-h2h markets (e.g. totals/BTTS) are out of scope for this phase and
    are skipped, not mapped.
    """
    quotes: list[OddsQuote] = []
    for bookmaker_dto in dto.bookmakers:
        if bookmaker_dto.key != sharp_bookmaker_key:
            continue
        bookmaker = Bookmaker(name=bookmaker_dto.title, is_sharp=True, region=region)
        for market_dto in bookmaker_dto.markets:
            if market_dto.key != "h2h":
                continue
            quoted_at = (
                market_dto.last_update or bookmaker_dto.last_update or datetime.now(timezone.utc)
            )
            for outcome in market_dto.outcomes:
                selection = Selection(
                    market_type=MarketType.MATCH_WINNER_1X2,
                    outcome=_outcome_label(outcome.name, dto),
                )
                quotes.append(
                    OddsQuote(
                        bookmaker=bookmaker,
                        selection=selection,
                        odds=DecimalOdds(outcome.price),
                        quoted_at=quoted_at.astimezone(timezone.utc),
                    )
                )
    return quotes


def _team_score(event: ScoreEventDTO, team_name: str) -> int | None:
    if event.scores is None:
        return None
    for entry in event.scores:
        if entry.name == team_name and entry.score is not None:
            try:
                return int(entry.score)
            except ValueError:
                return None
    return None


def team_form_from_score_events(team: Team, events: Sequence[ScoreEventDTO]) -> TeamForm:
    """Aggregate up to the last 10 *completed* events involving `team` (most
    recent first) into a TeamForm. Events that aren't completed, don't
    involve this team, or are missing usable scores are skipped entirely -
    they don't count against the 10, they just aren't there.
    """
    played: list[tuple[datetime, int, int]] = []
    for event in events:
        if not event.completed:
            continue
        if team.name not in (event.home_team, event.away_team):
            continue
        opponent_name = event.away_team if event.home_team == team.name else event.home_team
        team_goals = _team_score(event, team.name)
        opponent_goals = _team_score(event, opponent_name)
        if team_goals is None or opponent_goals is None:
            continue
        played.append((event.commence_time, team_goals, opponent_goals))

    played.sort(key=lambda item: item[0], reverse=True)
    last_ten = played[:_FORM_WINDOW]

    wins = draws = losses = goals_for = goals_against = 0
    for _, team_goals, opponent_goals in last_ten:
        goals_for += team_goals
        goals_against += opponent_goals
        if team_goals > opponent_goals:
            wins += 1
        elif team_goals == opponent_goals:
            draws += 1
        else:
            losses += 1

    return TeamForm(
        team=team,
        matches_played=len(last_ten),
        wins=wins,
        draws=draws,
        losses=losses,
        goals_for=goals_for,
        goals_against=goals_against,
    )
