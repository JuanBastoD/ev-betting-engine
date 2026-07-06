"""GET /value-bets tests - persists ValueBets directly via the real
repository (bypassing the pipeline, since this endpoint only reads), then
checks the listing/filtering behaves as expected end to end through HTTP.
"""

from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

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
from src.infrastructure.persistence.repositories.value_bet_repository import (
    SqlAlchemyValueBetRepository,
)


def _match(match_id: str, league_id: str, kickoff: datetime) -> Match:
    home = Team(id=f"{match_id}-home", name="Home")
    away = Team(id=f"{match_id}-away", name="Away")
    return Match(
        id=match_id, home_team=home, away_team=away,
        league=League(id=league_id, name=league_id), kickoff_utc=kickoff,
    )


def _bet(
    match: Match, *, market_type: MarketType = MarketType.MATCH_WINNER_1X2, edge: float = 10.0,
    model_source: ModelSource = ModelSource.MARKET, lineup_confirmed: bool | None = None,
) -> ValueBet:
    return ValueBet(
        match=match, selection=Selection(market_type=market_type, outcome="Home"),
        local_odds=DecimalOdds(2.20), fair_probability=Probability(0.5), edge=EdgePercentage(edge),
        suggested_stake=Stake(0.05), model_source=model_source, lineup_confirmed=lineup_confirmed,
    )


@pytest.fixture
def match_a() -> Match:
    return _match("match-a", "league-1", datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc))


@pytest.fixture
def match_b() -> Match:
    return _match("match-b", "league-2", datetime(2026, 8, 16, 20, 0, tzinfo=timezone.utc))


async def test_list_value_bets_with_no_filters(
    client: httpx.AsyncClient, session: AsyncSession, match_a: Match
) -> None:
    repository = SqlAlchemyValueBetRepository(session)
    await repository.save(_bet(match_a))
    await session.flush()

    response = await client.get("/value-bets")

    assert response.status_code == 200
    assert len(response.json()["value_bets"]) == 1


async def test_list_value_bets_filters_by_league(
    client: httpx.AsyncClient, session: AsyncSession, match_a: Match, match_b: Match
) -> None:
    repository = SqlAlchemyValueBetRepository(session)
    await repository.save(_bet(match_a))
    await repository.save(_bet(match_b))
    await session.flush()

    response = await client.get("/value-bets", params={"league_id": "league-1"})

    assert response.status_code == 200
    bets = response.json()["value_bets"]
    assert len(bets) == 1
    assert bets[0]["match_id"] == "match-a"


async def test_list_value_bets_filters_by_market_type(
    client: httpx.AsyncClient, session: AsyncSession, match_a: Match
) -> None:
    repository = SqlAlchemyValueBetRepository(session)
    await repository.save(_bet(match_a, market_type=MarketType.MATCH_WINNER_1X2))
    await repository.save(_bet(match_a, market_type=MarketType.PLAYER_PROP, model_source=ModelSource.STATISTICAL, lineup_confirmed=True))
    await session.flush()

    response = await client.get("/value-bets", params={"market_type": "PLAYER_PROP"})

    assert response.status_code == 200
    bets = response.json()["value_bets"]
    assert len(bets) == 1
    assert bets[0]["market_type"] == "PLAYER_PROP"
    assert bets[0]["lineup_confirmed"] is True


async def test_list_value_bets_filters_by_model_source(
    client: httpx.AsyncClient, session: AsyncSession, match_a: Match
) -> None:
    repository = SqlAlchemyValueBetRepository(session)
    await repository.save(_bet(match_a, model_source=ModelSource.MARKET))
    await repository.save(_bet(match_a, model_source=ModelSource.BOTH))
    await session.flush()

    response = await client.get("/value-bets", params={"model_source": "BOTH"})

    assert response.status_code == 200
    bets = response.json()["value_bets"]
    assert len(bets) == 1
    assert bets[0]["model_source"] == "BOTH"


async def test_list_value_bets_filters_by_min_ev_threshold(
    client: httpx.AsyncClient, session: AsyncSession, match_a: Match
) -> None:
    repository = SqlAlchemyValueBetRepository(session)
    await repository.save(_bet(match_a, edge=1.0))
    await repository.save(_bet(match_a, edge=15.0))
    await session.flush()

    response = await client.get("/value-bets", params={"min_ev_threshold": 0.1})

    assert response.status_code == 200
    bets = response.json()["value_bets"]
    assert len(bets) == 1
    assert bets[0]["edge_percentage"] == 15.0


async def test_list_value_bets_filters_by_match_date(
    client: httpx.AsyncClient, session: AsyncSession, match_a: Match, match_b: Match
) -> None:
    repository = SqlAlchemyValueBetRepository(session)
    await repository.save(_bet(match_a))
    await repository.save(_bet(match_b))
    await session.flush()

    response = await client.get("/value-bets", params={"match_date": "2026-08-15"})

    assert response.status_code == 200
    bets = response.json()["value_bets"]
    assert len(bets) == 1
    assert bets[0]["match_id"] == "match-a"


async def test_list_value_bets_returns_empty_when_none_persisted(client: httpx.AsyncClient) -> None:
    response = await client.get("/value-bets")

    assert response.status_code == 200
    assert response.json()["value_bets"] == []


async def test_market_bet_has_null_lineup_confirmed(
    client: httpx.AsyncClient, session: AsyncSession, match_a: Match
) -> None:
    repository = SqlAlchemyValueBetRepository(session)
    await repository.save(_bet(match_a))
    await session.flush()

    response = await client.get("/value-bets")

    assert response.json()["value_bets"][0]["lineup_confirmed"] is None
