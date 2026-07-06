from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.bet_result import BetResult
from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.selection import Selection
from src.domain.entities.settled_bet import SettledBet
from src.domain.entities.value_bet import ValueBet
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.edge_percentage import EdgePercentage
from src.domain.value_objects.probability import Probability
from src.domain.value_objects.stake import Stake
from src.infrastructure.persistence.repositories.match_repository import SqlAlchemyMatchRepository
from src.infrastructure.persistence.repositories.settled_bet_repository import (
    SqlAlchemySettledBetRepository,
)


def _settled_bet(
    match: Match,
    selection: Selection,
    *,
    bookmaker: Bookmaker | None = None,
    result: BetResult = BetResult.WON,
    closing_sharp_odds: float | None = None,
) -> SettledBet:
    value_bet = ValueBet(
        match=match,
        selection=selection,
        local_odds=DecimalOdds(2.20),
        fair_probability=Probability(0.5),
        edge=EdgePercentage(10.0),
        suggested_stake=Stake(25.0),
        model_source=ModelSource.MARKET,
        bookmaker=bookmaker,
    )
    return SettledBet(
        value_bet=value_bet,
        result=result,
        settled_at=datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc),
        closing_sharp_odds=DecimalOdds(closing_sharp_odds) if closing_sharp_odds else None,
    )


async def test_save_and_list_all_round_trip(
    session: AsyncSession, match: Match, selection: Selection, bookmaker: Bookmaker
) -> None:
    settled_bet = _settled_bet(match, selection, bookmaker=bookmaker, closing_sharp_odds=2.00)
    repository = SqlAlchemySettledBetRepository(session)

    await repository.save(settled_bet)

    results = await repository.list_all()

    assert results == [settled_bet]


async def test_save_without_bookmaker_round_trips_with_none(
    session: AsyncSession, match: Match, selection: Selection
) -> None:
    settled_bet = _settled_bet(match, selection)
    repository = SqlAlchemySettledBetRepository(session)

    await repository.save(settled_bet)

    results = await repository.list_all()

    assert results == [settled_bet]
    assert results[0].value_bet.bookmaker is None


async def test_save_upserts_the_nested_match_without_a_prior_match_save(
    session: AsyncSession, match: Match, selection: Selection
) -> None:
    settled_bet = _settled_bet(match, selection)
    await SqlAlchemySettledBetRepository(session).save(settled_bet)

    persisted_match = await SqlAlchemyMatchRepository(session).get_by_id(match.id)

    assert persisted_match == match


async def test_list_all_returns_empty_list_when_nothing_settled(session: AsyncSession) -> None:
    repository = SqlAlchemySettledBetRepository(session)
    assert await repository.list_all() == []


async def test_list_all_returns_multiple_settled_bets(
    session: AsyncSession, match: Match, selection: Selection
) -> None:
    repository = SqlAlchemySettledBetRepository(session)
    await repository.save(_settled_bet(match, selection, result=BetResult.WON))
    await repository.save(_settled_bet(match, selection, result=BetResult.LOST))

    results = await repository.list_all()

    assert {sb.result for sb in results} == {BetResult.WON, BetResult.LOST}
