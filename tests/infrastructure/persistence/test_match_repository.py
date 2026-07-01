from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.league import League
from src.domain.entities.match import Match
from src.domain.entities.team import Team
from src.infrastructure.persistence.repositories.match_repository import SqlAlchemyMatchRepository


async def test_save_and_get_by_id_round_trip(session: AsyncSession, match: Match) -> None:
    repository = SqlAlchemyMatchRepository(session)

    await repository.save(match)
    retrieved = await repository.get_by_id(match.id)

    assert retrieved == match


async def test_get_by_id_returns_none_when_missing(session: AsyncSession) -> None:
    repository = SqlAlchemyMatchRepository(session)

    assert await repository.get_by_id("does-not-exist") is None


async def test_save_upserts_an_existing_match(
    session: AsyncSession, match: Match, home_team: Team, away_team: Team, league: League
) -> None:
    repository = SqlAlchemyMatchRepository(session)
    await repository.save(match)

    new_kickoff = match.kickoff_utc + timedelta(days=1)
    updated_match = Match(
        id=match.id,
        home_team=home_team,
        away_team=away_team,
        league=league,
        kickoff_utc=new_kickoff,
    )
    await repository.save(updated_match)

    retrieved = await repository.get_by_id(match.id)

    assert retrieved is not None
    assert retrieved.kickoff_utc == new_kickoff


async def test_list_upcoming_returns_only_future_matches_ordered_by_kickoff(
    session: AsyncSession, home_team: Team, away_team: Team, league: League
) -> None:
    now = datetime.now(timezone.utc)
    past_match = Match(
        id="match-past",
        home_team=home_team,
        away_team=away_team,
        league=league,
        kickoff_utc=now - timedelta(days=1),
    )
    soon_match = Match(
        id="match-soon",
        home_team=home_team,
        away_team=away_team,
        league=league,
        kickoff_utc=now + timedelta(hours=1),
    )
    later_match = Match(
        id="match-later",
        home_team=home_team,
        away_team=away_team,
        league=league,
        kickoff_utc=now + timedelta(days=1),
    )

    repository = SqlAlchemyMatchRepository(session)
    for a_match in (past_match, later_match, soon_match):
        await repository.save(a_match)

    upcoming = await repository.list_upcoming()

    assert [m.id for m in upcoming] == ["match-soon", "match-later"]
