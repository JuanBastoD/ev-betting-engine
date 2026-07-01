from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """A DateTime that always round-trips as timezone-aware UTC.

    SQLite (aiosqlite) has no native timezone-aware column type: it silently
    drops tzinfo on write and returns naive datetimes on read, which would
    violate the domain's invariant that Match/OddsQuote timestamps are UTC
    tz-aware. Postgres (asyncpg) already returns aware datetimes for
    TIMESTAMPTZ. Normalizing in both directions here means the same code path
    works on both, satisfying the "swap DATABASE_URL, not code" requirement.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime requires a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    """Registry for ORM models. Deliberately separate from domain entities -
    domain dataclasses are never used as tables; see mappers.py for the
    explicit Entity <-> Model conversion."""


class TeamModel(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)


class LeagueModel(Base):
    __tablename__ = "leagues"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)


class BookmakerModel(Base):
    __tablename__ = "bookmakers"
    __table_args__ = (UniqueConstraint("name", name="uq_bookmakers_name"),)

    # Surrogate PK: the domain Bookmaker entity has no id, only a unique name.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_sharp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False)


class MatchModel(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    home_team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id"), nullable=False, index=True
    )
    away_team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id"), nullable=False, index=True
    )
    league_id: Mapped[str] = mapped_column(ForeignKey("leagues.id"), nullable=False, index=True)
    kickoff_utc: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)

    home_team: Mapped[TeamModel] = relationship(foreign_keys=[home_team_id], lazy="selectin")
    away_team: Mapped[TeamModel] = relationship(foreign_keys=[away_team_id], lazy="selectin")
    league: Mapped[LeagueModel] = relationship(lazy="selectin")


class OddsQuoteModel(Base):
    __tablename__ = "odds_quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Nullable: the domain OddsQuote entity carries no match reference, so a
    # quote can be persisted stand-alone via the OddsRepository port's plain
    # `save(odds_quote)` signature. See repositories/odds_repository.py.
    match_id: Mapped[str | None] = mapped_column(
        ForeignKey("matches.id"), nullable=True, index=True
    )
    bookmaker_id: Mapped[int] = mapped_column(
        ForeignKey("bookmakers.id"), nullable=False, index=True
    )
    # Selection (domain) has no table of its own - flattened onto the quote.
    market_type: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    line: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_value: Mapped[float] = mapped_column(Float, nullable=False)
    quoted_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)

    match: Mapped[MatchModel | None] = relationship(lazy="selectin")
    bookmaker: Mapped[BookmakerModel] = relationship(lazy="selectin")


class TeamFormModel(Base):
    __tablename__ = "team_forms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    matches_played: Mapped[int] = mapped_column(Integer, nullable=False)
    wins: Mapped[int] = mapped_column(Integer, nullable=False)
    draws: Mapped[int] = mapped_column(Integer, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, nullable=False)
    goals_for: Mapped[int] = mapped_column(Integer, nullable=False)
    goals_against: Mapped[int] = mapped_column(Integer, nullable=False)

    team: Mapped[TeamModel] = relationship(lazy="selectin")


class ValueBetModel(Base):
    __tablename__ = "value_bets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), nullable=False, index=True)
    # Selection (domain) flattened onto the row, same rationale as OddsQuoteModel.
    market_type: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    line: Mapped[float | None] = mapped_column(Float, nullable=True)
    local_odds: Mapped[float] = mapped_column(Float, nullable=False)
    fair_probability: Mapped[float] = mapped_column(Float, nullable=False)
    edge_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    suggested_stake: Mapped[float] = mapped_column(Float, nullable=False)

    match: Mapped[MatchModel] = relationship(lazy="selectin")
