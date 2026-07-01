from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.league import League
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.selection import Selection
from src.domain.entities.team import Team
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.infrastructure.persistence.repositories.match_repository import SqlAlchemyMatchRepository
from src.infrastructure.persistence.repositories.odds_repository import SqlAlchemyOddsRepository


async def test_save_and_list_by_match_id_round_trip(
    session: AsyncSession, match: Match, bookmaker: Bookmaker, selection: Selection
) -> None:
    await SqlAlchemyMatchRepository(session).save(match)

    repository = SqlAlchemyOddsRepository(session)
    quote = OddsQuote(
        bookmaker=bookmaker,
        selection=selection,
        odds=DecimalOdds(1.95),
        quoted_at=datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc),
    )
    await repository.save(quote, match_id=match.id)

    quotes = await repository.list_by_match_id(match.id)

    assert quotes == [quote]


async def test_list_by_match_id_returns_empty_list_when_no_quotes_exist(
    session: AsyncSession,
) -> None:
    repository = SqlAlchemyOddsRepository(session)

    assert await repository.list_by_match_id("no-such-match") == []


async def test_save_without_match_id_is_abc_compliant_and_unassociated(
    session: AsyncSession, match: Match, bookmaker: Bookmaker, selection: Selection
) -> None:
    await SqlAlchemyMatchRepository(session).save(match)

    repository = SqlAlchemyOddsRepository(session)
    quote = OddsQuote(
        bookmaker=bookmaker,
        selection=selection,
        odds=DecimalOdds(1.95),
        quoted_at=datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc),
    )
    await repository.save(quote)  # exactly the OddsRepository.save(odds_quote) signature

    assert await repository.list_by_match_id(match.id) == []


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
    match_repository = SqlAlchemyMatchRepository(session)
    await match_repository.save(match_a)
    await match_repository.save(match_b)

    odds_repository = SqlAlchemyOddsRepository(session)
    selection = Selection(market_type=MarketType.MATCH_WINNER_1X2, outcome="Home")
    later_quote = OddsQuote(
        bookmaker=Bookmaker(name="Bet365", is_sharp=False, region="UK"),
        selection=selection,
        odds=DecimalOdds(1.90),
        quoted_at=datetime(2026, 8, 15, 19, 0, tzinfo=timezone.utc),
    )
    earlier_quote = OddsQuote(
        bookmaker=Bookmaker(name="Pinnacle", is_sharp=True, region="EU"),
        selection=selection,
        odds=DecimalOdds(1.95),
        quoted_at=datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc),
    )
    other_match_quote = OddsQuote(
        bookmaker=Bookmaker(name="Bwin", is_sharp=False, region="EU"),
        selection=selection,
        odds=DecimalOdds(2.0),
        quoted_at=datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc),
    )

    await odds_repository.save(later_quote, match_id=match_a.id)
    await odds_repository.save(earlier_quote, match_id=match_a.id)
    await odds_repository.save(other_match_quote, match_id=match_b.id)

    quotes = await odds_repository.list_by_match_id(match_a.id)

    assert [quote.bookmaker.name for quote in quotes] == ["Pinnacle", "Bet365"]
