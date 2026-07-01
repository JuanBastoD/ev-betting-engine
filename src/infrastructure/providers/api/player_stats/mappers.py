"""DTO -> domain Entity mapping (Anti-Corruption Layer) for the Sportmonks
player_stats module.

The domain never sees a PlayerFixtureStatsDTO/InjuryEntryDTO/LineupEntryDTO -
this is the only module allowed to know both shapes exist.
"""

from collections.abc import Sequence
from datetime import timezone

from src.domain.entities.injury_status import InjuryStatus
from src.domain.entities.injury_status_type import InjuryStatusType
from src.domain.entities.league import League
from src.domain.entities.lineup_confirmation import LineupConfirmation
from src.domain.entities.match import Match
from src.domain.entities.player import Player
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_position import PlayerPosition
from src.domain.entities.team import Team
from src.domain.value_objects.probability import Probability
from src.infrastructure.providers.api.player_stats.dtos import (
    FixtureRefDTO,
    InjuryEntryDTO,
    LineupEntryDTO,
    PlayerFixtureStatsDTO,
    PlayerRefDTO,
)

_POSITION_MAP: dict[str, PlayerPosition] = {
    "goalkeeper": PlayerPosition.GOALKEEPER,
    "gk": PlayerPosition.GOALKEEPER,
    "defender": PlayerPosition.DEFENDER,
    "df": PlayerPosition.DEFENDER,
    "midfielder": PlayerPosition.MIDFIELDER,
    "mf": PlayerPosition.MIDFIELDER,
    "forward": PlayerPosition.FORWARD,
    "attacker": PlayerPosition.FORWARD,
    "fw": PlayerPosition.FORWARD,
}

_INJURY_STATUS_MAP: dict[str, InjuryStatusType] = {
    "fit": InjuryStatusType.FIT,
    "doubtful": InjuryStatusType.DOUBTFUL,
    "questionable": InjuryStatusType.DOUBTFUL,
    "injured": InjuryStatusType.INJURED,
    "out": InjuryStatusType.INJURED,
    "suspended": InjuryStatusType.SUSPENDED,
}


def _position_from_raw(raw: str | None) -> PlayerPosition:
    if raw is None:
        return PlayerPosition.UNKNOWN
    return _POSITION_MAP.get(raw.strip().lower(), PlayerPosition.UNKNOWN)


def _team_from_ref(team_id: str, team_name: str) -> Team:
    # Unlike the sibling odds module, Sportmonks gives a real team id here -
    # no name-slugging fallback needed.
    return Team(id=team_id, name=team_name)


def _league_from_ref(league_id: str, league_name: str | None) -> League:
    return League(id=league_id, name=league_name or league_id)


def match_from_fixture_ref(ref: FixtureRefDTO) -> Match:
    return Match(
        id=ref.id,
        home_team=_team_from_ref(ref.home_team_id, ref.home_team_name),
        away_team=_team_from_ref(ref.away_team_id, ref.away_team_name),
        league=_league_from_ref(ref.league_id, ref.league_name),
        kickoff_utc=ref.starting_at.astimezone(timezone.utc),
    )


def player_from_player_ref(ref: PlayerRefDTO) -> Player:
    return Player(
        id=ref.id,
        name=ref.name,
        team=_team_from_ref(ref.team_id, ref.team_name),
        position=_position_from_raw(ref.position),
    )


def player_from_injury_entry(entry: InjuryEntryDTO) -> Player:
    return Player(
        id=entry.player_id,
        name=entry.player_name,
        team=_team_from_ref(entry.team_id, entry.team_name),
        position=_position_from_raw(entry.position),
    )


def player_from_lineup_entry(entry: LineupEntryDTO) -> Player:
    return Player(
        id=entry.player_id,
        name=entry.player_name,
        team=_team_from_ref(entry.team_id, entry.team_name),
        position=_position_from_raw(entry.position),
    )


def player_match_stats_from_dto(dto: PlayerFixtureStatsDTO) -> PlayerMatchStats:
    return PlayerMatchStats(
        match=match_from_fixture_ref(dto.fixture),
        player=player_from_player_ref(dto.player),
        minutes_played=dto.minutes_played,
        started=dto.started,
        shots_total=dto.shots_total,
        shots_on_target=dto.shots_on_target,
        goals=dto.goals,
        assists=dto.assists,
        yellow_cards=dto.yellow_cards,
        red_cards=dto.red_cards,
        corners_won=dto.corners_won,
    )


def _normalize_injury_status(raw: str) -> InjuryStatusType | None:
    return _INJURY_STATUS_MAP.get(raw.strip().lower())


def injury_status_from_entry(entry: InjuryEntryDTO) -> InjuryStatus | None:
    """Returns None (rather than guessing) when `entry.status` doesn't map
    onto InjuryStatusType - see injury_statuses_from_entries for why."""
    status = _normalize_injury_status(entry.status)
    if status is None:
        return None
    return InjuryStatus(
        player=player_from_injury_entry(entry),
        status=status,
        source=entry.source,
        updated_at=entry.updated_at.astimezone(timezone.utc),
    )


def injury_statuses_from_entries(entries: Sequence[InjuryEntryDTO]) -> list[InjuryStatus]:
    """Silently drops entries whose status string doesn't map onto
    InjuryStatusType. Guessing FIT for an unrecognized status would risk
    treating an actually-unavailable player as available; skipping just
    means no injury signal is reported for that player, which is the safer
    failure mode for a betting-risk system.
    """
    results: list[InjuryStatus] = []
    for entry in entries:
        mapped = injury_status_from_entry(entry)
        if mapped is not None:
            results.append(mapped)
    return results


def estimate_start_probability(recent_matches: Sequence[PlayerMatchStats]) -> Probability:
    """% of `recent_matches` in which the player started.

    With no history at all, 0.5 (maximum uncertainty) is used rather than
    0.0: there's no signal either way, and 0.0 would assert confidently that
    the player won't start, which "no data" doesn't actually support.
    """
    if not recent_matches:
        return Probability(0.5)
    starts = sum(1 for stats in recent_matches if stats.started)
    return Probability(starts / len(recent_matches))


def lineup_confirmation_from_entry(
    entry: LineupEntryDTO, match: Match, *, is_confirmed: bool, start_probability: Probability
) -> LineupConfirmation:
    """Pure mapping - the caller (SportmonksPlayerStatsProvider) computes
    `start_probability` beforehand: 1.0/0.0 from the official entry when
    confirmed, or via estimate_start_probability over that player's recent
    matches when not.
    """
    return LineupConfirmation(
        player=player_from_lineup_entry(entry),
        match=match,
        is_starting=start_probability.value >= 0.5,
        is_confirmed=is_confirmed,
        start_probability=start_probability,
    )
