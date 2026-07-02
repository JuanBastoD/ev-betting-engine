from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.league import League
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.selection import Selection
from src.domain.entities.team import Team
from src.domain.entities.value_bet import ValueBet
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.edge_percentage import EdgePercentage
from src.domain.value_objects.probability import Probability
from src.domain.value_objects.stake import Stake
from src.infrastructure.persistence.repositories.match_repository import SqlAlchemyMatchRepository
from src.infrastructure.persistence.repositories.value_bet_repository import (
    SqlAlchemyValueBetRepository,
)


def _value_bet(match: Match, selection: Selection, edge: float = 10.0) -> ValueBet:
    return ValueBet(
        match=match,
        selection=selection,
        local_odds=DecimalOdds(2.20),
        fair_probability=Probability(0.5),
        edge=EdgePercentage(edge),
        suggested_stake=Stake(25.0),
        model_source=ModelSource.MARKET,
    )


async def test_save_and_list_by_match_id_round_trip(
    session: AsyncSession, match: Match, selection: Selection
) -> None:
    value_bet = _value_bet(match, selection)
    repository = SqlAlchemyValueBetRepository(session)

    await repository.save(value_bet)

    results = await repository.list_by_match_id(match.id)

    assert results == [value_bet]


async def test_save_upserts_the_nested_match_without_a_prior_match_save(
    session: AsyncSession, match: Match, selection: Selection
) -> None:
    value_bet = _value_bet(match, selection)
    await SqlAlchemyValueBetRepository(session).save(value_bet)

    persisted_match = await SqlAlchemyMatchRepository(session).get_by_id(match.id)

    assert persisted_match == match


async def test_list_all_returns_value_bets_across_matches(
    session: AsyncSession, home_team: Team, away_team: Team, league: League, selection: Selection
) -> None:
    match_a = Match(
        id="match-a",
        home_team=home_team,
        away_team=away_team,
        league=league,
        kickoff_utc=datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc),
    )
    match_b = Match(
        id="match-b",
        home_team=home_team,
        away_team=away_team,
        league=league,
        kickoff_utc=datetime(2026, 8, 16, 20, 0, tzinfo=timezone.utc),
    )

    repository = SqlAlchemyValueBetRepository(session)
    await repository.save(_value_bet(match_a, selection, edge=5.0))
    await repository.save(_value_bet(match_b, selection, edge=8.0))

    all_bets = await repository.list_all()

    assert {value_bet.match.id for value_bet in all_bets} == {"match-a", "match-b"}


async def test_list_by_match_id_returns_empty_list_when_no_value_bets_exist(
    session: AsyncSession,
) -> None:
    repository = SqlAlchemyValueBetRepository(session)

    assert await repository.list_by_match_id("no-such-match") == []
