"""Pydantic DTOs for the Sportmonks Football API v3 (player_stats module).

Modeled on Sportmonks' well-documented conventions (a `data` envelope on
every response, `api_token` query-param auth) but simplified/flattened where
the exact real wire shape is uncertain without API docs in hand - notably,
the real fixture-lineup endpoint nests per-player stats under
`lineups[].details[]` as generic type_id/value pairs, which this adapter
assumes has already been flattened into named fields by the time it reaches
these DTOs. Verify field names against current Sportmonks docs before
pointing this at production traffic.

Nothing outside this package is allowed to see these - mappers.py is the
only place that turns them into domain entities.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FixtureRefDTO(BaseModel):
    """Fixture context embedded alongside player-level data, analogous to
    how EventOddsDTO in the sibling odds module embeds match context -
    avoids ever needing a bare match_id with no way to build a full Match."""

    model_config = ConfigDict(extra="ignore")

    id: str
    starting_at: datetime
    league_id: str
    league_name: str | None = None
    home_team_id: str
    home_team_name: str
    away_team_id: str
    away_team_name: str


class PlayerRefDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    team_id: str
    team_name: str
    position: str | None = None


class PlayerFixtureStatsDTO(BaseModel):
    """One player's statistical line for one fixture."""

    model_config = ConfigDict(extra="ignore")

    fixture: FixtureRefDTO
    player: PlayerRefDTO
    minutes_played: int
    started: bool
    shots_total: int = 0
    shots_on_target: int = 0
    goals: int = 0
    assists: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    corners_won: int | None = None


class InjuryEntryDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    player_id: str
    player_name: str
    team_id: str
    team_name: str
    position: str | None = None
    status: str
    source: str
    updated_at: datetime


class LineupEntryDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    player_id: str
    player_name: str
    team_id: str
    team_name: str
    position: str | None = None
    is_starting: bool


class FixtureLineupDTO(BaseModel):
    """Response shape of the fixture-lineup endpoint.

    `is_confirmed` mirrors a real Sportmonks signal: the lineups collection
    on a fixture is only populated once the official lineup is announced
    (typically ~1h before kickoff); before that, it's either absent or
    holds a provider "predicted lineup" instead - either way `entries` may
    be non-empty with `is_confirmed=False`.
    """

    model_config = ConfigDict(extra="ignore")

    fixture: FixtureRefDTO
    is_confirmed: bool
    entries: list[LineupEntryDTO] = Field(default_factory=list)
