from datetime import date, datetime, timezone

import pytest

from src.application.use_cases.list_value_bets import ListValueBetsUseCase, ValueBetFilters
from src.domain.entities.league import League
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.selection import Selection
from src.domain.entities.team import Team
from src.domain.entities.value_bet import ValueBet
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.edge_percentage import EdgePercentage
from src.domain.value_objects.probability import Probability
from src.domain.value_objects.stake import Stake
from tests.fakes import FakeValueBetRepository


def _match(match_id: str, league_obj: League, kickoff: datetime, home: Team, away: Team) -> Match:
    return Match(id=match_id, home_team=home, away_team=away, league=league_obj, kickoff_utc=kickoff)


def _bet(
    match: Match, *, market_type: MarketType = MarketType.MATCH_WINNER_1X2, edge: float = 10.0,
    model_source: ModelSource = ModelSource.MARKET,
) -> ValueBet:
    return ValueBet(
        match=match, selection=Selection(market_type=market_type, outcome="Home"),
        local_odds=DecimalOdds(2.20), fair_probability=Probability(0.5), edge=EdgePercentage(edge),
        suggested_stake=Stake(0.05), model_source=model_source,
    )


@pytest.fixture
def teams() -> tuple[Team, Team]:
    return Team(id="h", name="Home"), Team(id="a", name="Away")


async def test_execute_with_no_filters_returns_everything(teams: tuple[Team, Team]) -> None:
    home, away = teams
    league_a = League(id="league-a", name="A")
    match = _match("m1", league_a, datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc), home, away)
    repository = FakeValueBetRepository()
    await repository.save(_bet(match))
    use_case = ListValueBetsUseCase(value_bet_repository=repository)

    results = await use_case.execute()

    assert len(results) == 1


async def test_filters_by_league(teams: tuple[Team, Team]) -> None:
    home, away = teams
    league_a = League(id="league-a", name="A")
    league_b = League(id="league-b", name="B")
    kickoff = datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc)
    match_a = _match("m1", league_a, kickoff, home, away)
    match_b = _match("m2", league_b, kickoff, home, away)
    repository = FakeValueBetRepository()
    await repository.save(_bet(match_a))
    await repository.save(_bet(match_b))
    use_case = ListValueBetsUseCase(value_bet_repository=repository)

    results = await use_case.execute(ValueBetFilters(league_id="league-a"))

    assert [vb.match.id for vb in results] == ["m1"]


async def test_filters_by_min_ev_threshold(teams: tuple[Team, Team]) -> None:
    home, away = teams
    league_a = League(id="league-a", name="A")
    kickoff = datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc)
    match = _match("m1", league_a, kickoff, home, away)
    repository = FakeValueBetRepository()
    await repository.save(_bet(match, edge=1.0))  # 1% edge
    await repository.save(_bet(match, edge=10.0))  # 10% edge
    use_case = ListValueBetsUseCase(value_bet_repository=repository)

    results = await use_case.execute(ValueBetFilters(min_ev_threshold=0.05))

    assert len(results) == 1
    assert results[0].edge.value == 10.0


async def test_filters_by_match_date(teams: tuple[Team, Team]) -> None:
    home, away = teams
    league_a = League(id="league-a", name="A")
    match_early = _match("m1", league_a, datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc), home, away)
    match_late = _match("m2", league_a, datetime(2026, 8, 16, 20, 0, tzinfo=timezone.utc), home, away)
    repository = FakeValueBetRepository()
    await repository.save(_bet(match_early))
    await repository.save(_bet(match_late))
    use_case = ListValueBetsUseCase(value_bet_repository=repository)

    results = await use_case.execute(ValueBetFilters(match_date=date(2026, 8, 15)))

    assert [vb.match.id for vb in results] == ["m1"]


async def test_filters_by_market_type(teams: tuple[Team, Team]) -> None:
    home, away = teams
    league_a = League(id="league-a", name="A")
    kickoff = datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc)
    match = _match("m1", league_a, kickoff, home, away)
    repository = FakeValueBetRepository()
    await repository.save(_bet(match, market_type=MarketType.MATCH_WINNER_1X2))
    await repository.save(_bet(match, market_type=MarketType.PLAYER_PROP))
    use_case = ListValueBetsUseCase(value_bet_repository=repository)

    results = await use_case.execute(ValueBetFilters(market_type=MarketType.PLAYER_PROP))

    assert len(results) == 1
    assert results[0].selection.market_type is MarketType.PLAYER_PROP


async def test_filters_by_model_source(teams: tuple[Team, Team]) -> None:
    home, away = teams
    league_a = League(id="league-a", name="A")
    kickoff = datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc)
    match = _match("m1", league_a, kickoff, home, away)
    repository = FakeValueBetRepository()
    await repository.save(_bet(match, model_source=ModelSource.MARKET))
    await repository.save(_bet(match, model_source=ModelSource.BOTH))
    use_case = ListValueBetsUseCase(value_bet_repository=repository)

    results = await use_case.execute(ValueBetFilters(model_source=ModelSource.BOTH))

    assert len(results) == 1
    assert results[0].model_source is ModelSource.BOTH


async def test_filters_combine_with_and_semantics(teams: tuple[Team, Team]) -> None:
    home, away = teams
    league_a = League(id="league-a", name="A")
    league_b = League(id="league-b", name="B")
    kickoff = datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc)
    match_a = _match("m1", league_a, kickoff, home, away)
    match_b = _match("m2", league_b, kickoff, home, away)
    repository = FakeValueBetRepository()
    await repository.save(_bet(match_a, edge=10.0))
    await repository.save(_bet(match_b, edge=10.0))
    use_case = ListValueBetsUseCase(value_bet_repository=repository)

    results = await use_case.execute(
        ValueBetFilters(league_id="league-a", min_ev_threshold=0.05)
    )

    assert [vb.match.id for vb in results] == ["m1"]
