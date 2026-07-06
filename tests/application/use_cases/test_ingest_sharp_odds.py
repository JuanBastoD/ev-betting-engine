from datetime import datetime, timezone

import pytest

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.selection import Selection
from src.domain.entities.team import Team
from src.domain.entities.team_form import TeamForm
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.application.use_cases.ingest_sharp_odds import IngestSharpOddsUseCase
from tests.fakes import FakeMatchRepository, FakeOddsRepository, FakeSharpOddsProvider, FakeStatsProvider

SHARP_BOOKMAKER = Bookmaker(name="Pinnacle", is_sharp=True, region="EU")


def _quote(match: Match, outcome: str, odds_value: float) -> OddsQuote:
    return OddsQuote(
        match=match,
        bookmaker=SHARP_BOOKMAKER,
        selection=Selection(market_type=MarketType.MATCH_WINNER_1X2, outcome=outcome),
        odds=DecimalOdds(odds_value),
        quoted_at=datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def home_form(home_team: Team) -> TeamForm:
    return TeamForm(
        team=home_team, matches_played=10, wins=6, draws=2, losses=2, goals_for=11, goals_against=9
    )


@pytest.fixture
def away_form(away_team: Team) -> TeamForm:
    return TeamForm(
        team=away_team, matches_played=10, wins=2, draws=2, losses=6, goals_for=9, goals_against=11
    )


async def test_execute_saves_match_and_odds_and_returns_team_forms(
    match: Match, home_team: Team, away_team: Team, home_form: TeamForm, away_form: TeamForm
) -> None:
    quotes = [_quote(match, "Home", 2.00), _quote(match, "Draw", 3.40), _quote(match, "Away", 4.00)]
    sharp_odds_provider = FakeSharpOddsProvider({match.id: quotes})
    stats_provider = FakeStatsProvider({home_team.id: home_form, away_team.id: away_form})
    match_repository = FakeMatchRepository()
    odds_repository = FakeOddsRepository()

    use_case = IngestSharpOddsUseCase(
        sharp_odds_provider=sharp_odds_provider,
        stats_provider=stats_provider,
        match_repository=match_repository,
        odds_repository=odds_repository,
    )

    result = await use_case.execute(match)

    assert result.match is match
    assert result.sharp_quotes == quotes
    assert result.home_form is home_form
    assert result.away_form is away_form
    assert await match_repository.get_by_id(match.id) == match
    assert odds_repository.saved == quotes


async def test_execute_with_no_sharp_odds_available_still_registers_the_match(
    match: Match, home_team: Team, away_team: Team, home_form: TeamForm, away_form: TeamForm
) -> None:
    sharp_odds_provider = FakeSharpOddsProvider({})
    stats_provider = FakeStatsProvider({home_team.id: home_form, away_team.id: away_form})
    match_repository = FakeMatchRepository()
    odds_repository = FakeOddsRepository()

    use_case = IngestSharpOddsUseCase(
        sharp_odds_provider=sharp_odds_provider,
        stats_provider=stats_provider,
        match_repository=match_repository,
        odds_repository=odds_repository,
    )

    result = await use_case.execute(match)

    assert result.sharp_quotes == []
    assert odds_repository.saved == []
    assert await match_repository.get_by_id(match.id) == match
