"""Shared get-or-create/update helpers for the reference entities (Team,
League, Bookmaker) that Match/OddsQuote/ValueBet carry as nested objects but
that have no dedicated domain repository port of their own.

Used by the concrete repositories in repositories/ so a Match (or a ValueBet,
which nests one) can be saved in a single call without every caller having to
persist its Team/League/Bookmaker beforehand.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.league import League
from src.domain.entities.match import Match
from src.domain.entities.player import Player
from src.domain.entities.team import Team
from src.infrastructure.persistence.mappers import (
    league_to_model,
    match_to_model,
    player_to_model,
    team_to_model,
)
from src.infrastructure.persistence.models import (
    BookmakerModel,
    LeagueModel,
    MatchModel,
    PlayerModel,
    TeamModel,
)


async def upsert_team(session: AsyncSession, team: Team) -> None:
    model = await session.get(TeamModel, team.id)
    if model is None:
        session.add(team_to_model(team))
    else:
        model.name = team.name
        model.country = team.country


async def upsert_league(session: AsyncSession, league: League) -> None:
    model = await session.get(LeagueModel, league.id)
    if model is None:
        session.add(league_to_model(league))
    else:
        model.name = league.name
        model.country = league.country


async def upsert_bookmaker(session: AsyncSession, bookmaker: Bookmaker) -> int:
    """Get-or-create by the natural key (`name`, unique) and return the
    surrogate `id` FKs need, since the domain Bookmaker has none."""
    stmt = select(BookmakerModel).where(BookmakerModel.name == bookmaker.name)
    model = (await session.execute(stmt)).scalar_one_or_none()
    if model is None:
        model = BookmakerModel(
            name=bookmaker.name, is_sharp=bookmaker.is_sharp, region=bookmaker.region
        )
        session.add(model)
        await session.flush()
    else:
        model.is_sharp = bookmaker.is_sharp
        model.region = bookmaker.region
    return model.id


async def upsert_match(session: AsyncSession, match: Match) -> None:
    await upsert_team(session, match.home_team)
    await upsert_team(session, match.away_team)
    await upsert_league(session, match.league)
    await session.flush()

    model = await session.get(MatchModel, match.id)
    if model is None:
        session.add(match_to_model(match))
    else:
        model.home_team_id = match.home_team.id
        model.away_team_id = match.away_team.id
        model.league_id = match.league.id
        model.kickoff_utc = match.kickoff_utc
    await session.flush()


async def upsert_player(session: AsyncSession, player: Player) -> None:
    await upsert_team(session, player.team)
    await session.flush()

    model = await session.get(PlayerModel, player.id)
    if model is None:
        session.add(player_to_model(player))
    else:
        model.name = player.name
        model.team_id = player.team.id
        model.position = player.position.value
    await session.flush()
