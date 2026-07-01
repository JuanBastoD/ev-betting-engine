"""Pydantic DTOs mirroring The Odds API's raw JSON shapes (v4).

Nothing outside src/infrastructure/providers/api/ is allowed to see these -
mappers.py is the only place that turns them into domain entities. Raw JSON
never reaches the domain: if it doesn't fit these shapes, pydantic raises
ValidationError, which client.py translates into ProviderUnavailableError.

`extra="ignore"` on every model: the real API is free to add fields we don't
use yet without breaking us.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OutcomeDTO(BaseModel):
    """One priced outcome within a market, e.g. {"name": "Draw", "price": 3.4}."""

    model_config = ConfigDict(extra="ignore")

    name: str
    price: float
    point: float | None = None


class MarketDTO(BaseModel):
    """A single market (e.g. "h2h") offered by one bookmaker for one event."""

    model_config = ConfigDict(extra="ignore")

    key: str
    last_update: datetime | None = None
    outcomes: list[OutcomeDTO] = Field(default_factory=list)


class BookmakerDTO(BaseModel):
    """One bookmaker's markets for one event."""

    model_config = ConfigDict(extra="ignore")

    key: str
    title: str
    last_update: datetime | None = None
    markets: list[MarketDTO] = Field(default_factory=list)


class EventOddsDTO(BaseModel):
    """Response shape of both
    GET /sports/{sport}/odds (a list of these) and
    GET /sports/{sport}/events/{eventId}/odds (a single one)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    sport_key: str
    sport_title: str | None = None
    commence_time: datetime
    home_team: str
    away_team: str
    bookmakers: list[BookmakerDTO] = Field(default_factory=list)


class ScoreEntryDTO(BaseModel):
    """One team's score within a ScoreEventDTO. `score` is a string per the
    API and can be null/missing for events without a reported result yet."""

    model_config = ConfigDict(extra="ignore")

    name: str
    score: str | None = None


class ScoreEventDTO(BaseModel):
    """One element of GET /sports/{sport}/scores."""

    model_config = ConfigDict(extra="ignore")

    id: str
    sport_key: str
    commence_time: datetime
    completed: bool
    home_team: str
    away_team: str
    scores: list[ScoreEntryDTO] | None = None
    last_update: datetime | None = None
