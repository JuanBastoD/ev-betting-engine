from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.league import League
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.selection import Selection
from src.domain.entities.team import Team
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.infrastructure.persistence.models import BookmakerModel, MatchModel
from src.infrastructure.persistence.repositories.odds_repository import SqlAlchemyOddsRepository


async def test_save_and_list_by_match_id_round_trip(
    session: AsyncSession, match: Match, bookmaker: Bookmaker, selection: Selection
) -> None:
    repository = SqlAlchemyOddsRepository(session)
    quote = OddsQuote(
        match=match,
        bookmaker=bookmaker,
        selection=selection,
        odds=DecimalOdds(1.95),
        quoted_at=datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc),
    )
    await repository.save(quote)

    quotes = await repository.list_by_match_id(match.id)

    assert quotes == [quote]


async def test_list_by_match_id_returns_empty_list_when_no_quotes_exist(
    session: AsyncSession,
) -> None:
    repository = SqlAlchemyOddsRepository(session)

    assert await repository.list_by_match_id("no-such-match") == []


async def test_save_upserts_the_match_without_requiring_it_saved_first(
    session: AsyncSession, match: Match, bookmaker: Bookmaker, selection: Selection
) -> None:
    repository = SqlAlchemyOddsRepository(session)
    quote = OddsQuote(
        match=match,
        bookmaker=bookmaker,
        selection=selection,
        odds=DecimalOdds(1.95),
        quoted_at=datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc),
    )

    # No prior MatchRepository.save: the quote's own match satisfies the FK.
    await repository.save(quote)

    match_count = (
        await session.execute(
            select(func.count()).select_from(MatchModel).where(MatchModel.id == match.id)
        )
    ).scalar_one()
    assert match_count == 1


async def test_list_by_match_id_orders_by_quoted_at_and_excludes_other_matches(
    session: AsyncSession, home_team: Team, away_team: Team, league: League
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

    odds_repository = SqlAlchemyOddsRepository(session)
    selection = Selection(market_type=MarketType.MATCH_WINNER_1X2, outcome="Home")
    later_quote = OddsQuote(
        match=match_a,
        bookmaker=Bookmaker(name="Bet365", is_sharp=False, region="UK"),
        selection=selection,
        odds=DecimalOdds(1.90),
        quoted_at=datetime(2026, 8, 15, 19, 0, tzinfo=timezone.utc),
    )
    earlier_quote = OddsQuote(
        match=match_a,
        bookmaker=Bookmaker(name="Pinnacle", is_sharp=True, region="EU"),
        selection=selection,
        odds=DecimalOdds(1.95),
        quoted_at=datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc),
    )
    other_match_quote = OddsQuote(
        match=match_b,
        bookmaker=Bookmaker(name="Bwin", is_sharp=False, region="EU"),
        selection=selection,
        odds=DecimalOdds(2.0),
        quoted_at=datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc),
    )

    await odds_repository.save(later_quote)
    await odds_repository.save(earlier_quote)
    await odds_repository.save(other_match_quote)

    quotes = await odds_repository.list_by_match_id(match_a.id)

    assert [quote.bookmaker.name for quote in quotes] == ["Pinnacle", "Bet365"]


async def test_save_upserts_the_bookmaker_by_name_instead_of_duplicating_it(
    session: AsyncSession, match: Match, selection: Selection
) -> None:
    repository = SqlAlchemyOddsRepository(session)

    first_quote = OddsQuote(
        match=match,
        bookmaker=Bookmaker(name="Pinnacle", is_sharp=True, region="EU"),
        selection=selection,
        odds=DecimalOdds(1.90),
        quoted_at=datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc),
    )
    second_quote = OddsQuote(
        match=match,
        bookmaker=Bookmaker(name="Pinnacle", is_sharp=False, region="US"),
        selection=selection,
        odds=DecimalOdds(1.92),
        quoted_at=datetime(2026, 8, 15, 11, 0, tzinfo=timezone.utc),
    )

    await repository.save(first_quote)
    await repository.save(second_quote)

    bookmaker_count = (
        await session.execute(
            select(func.count()).select_from(BookmakerModel).where(BookmakerModel.name == "Pinnacle")
        )
    ).scalar_one()
    assert bookmaker_count == 1

    quotes = await repository.list_by_match_id(match.id)
    assert len(quotes) == 2
    # bookmakers is reference data (get-or-create by name), not a per-quote
    # snapshot: both quotes now see the latest upserted region/is_sharp.
    assert all(quote.bookmaker.region == "US" for quote in quotes)
    assert all(quote.bookmaker.is_sharp is False for quote in quotes)
