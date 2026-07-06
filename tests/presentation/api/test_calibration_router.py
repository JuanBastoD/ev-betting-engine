"""POST /value-bets/settle, GET /calibration/report, and POST
/calibration/factors/recompute tests - persists a real ValueBet via the
real repository, settles it through the endpoint, then reads it back via
the calibration endpoints end to end through HTTP."""

from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
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
from src.infrastructure.config import Settings
from src.infrastructure.persistence.repositories.value_bet_repository import (
    SqlAlchemyValueBetRepository,
)
from src.presentation.api.dependencies import get_settings


def _match(match_id: str = "match-a") -> Match:
    home = Team(id=f"{match_id}-home", name="Home")
    away = Team(id=f"{match_id}-away", name="Away")
    return Match(
        id=match_id,
        home_team=home,
        away_team=away,
        league=League(id="league-1", name="league-1"),
        kickoff_utc=datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc),
    )


def _bet(match: Match, *, fair_probability: float = 0.5) -> ValueBet:
    return ValueBet(
        match=match,
        selection=Selection(market_type=MarketType.MATCH_WINNER_1X2, outcome="Home"),
        local_odds=DecimalOdds(2.20),
        fair_probability=Probability(fair_probability),
        edge=EdgePercentage(10.0),
        suggested_stake=Stake(0.05),
        model_source=ModelSource.MARKET,
    )


async def _settle(
    client: httpx.AsyncClient, match: Match, *, result: str = "WON", closing_sharp_odds: float | None = None
) -> httpx.Response:
    return await client.post(
        "/value-bets/settle",
        json={
            "match_id": match.id,
            "market_type": "MATCH_WINNER_1X2",
            "outcome": "Home",
            "line": None,
            "local_odds": 2.20,
            "result": result,
            "settled_at": "2026-08-16T12:00:00Z",
            "closing_sharp_odds": closing_sharp_odds,
        },
    )


async def test_settle_bet_returns_the_settled_bet(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    match = _match()
    await SqlAlchemyValueBetRepository(session).save(_bet(match))
    await session.flush()

    response = await _settle(client, match, closing_sharp_odds=2.00)

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "WON"
    assert body["value_bet"]["match_id"] == match.id
    assert body["profit_loss"] == pytest.approx(0.05 * 1.20)
    assert body["clv"] is not None


async def test_settle_bet_returns_404_when_no_matching_value_bet(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    match = _match()

    response = await _settle(client, match)

    assert response.status_code == 404


async def test_calibration_report_reflects_settled_bets(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    match = _match()
    await SqlAlchemyValueBetRepository(session).save(_bet(match))
    await session.flush()
    settle_response = await _settle(client, match)
    assert settle_response.status_code == 200

    response = await client.get("/calibration/report")

    assert response.status_code == 200
    body = response.json()
    assert body["overall"]["sample_size"] == 1
    assert len(body["overall"]["calibration_curve"]) == 10


async def test_calibration_report_filters_by_model_source(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    match = _match()
    await SqlAlchemyValueBetRepository(session).save(_bet(match))
    await session.flush()
    await _settle(client, match)

    response = await client.get("/calibration/report", params={"model_source": "STATISTICAL"})

    assert response.status_code == 200
    assert response.json()["overall"]["sample_size"] == 0


async def test_calibration_report_filters_by_market_type(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    match = _match()
    await SqlAlchemyValueBetRepository(session).save(_bet(match))
    await session.flush()
    await _settle(client, match)

    response = await client.get("/calibration/report", params={"market_type": "MATCH_WINNER_1X2"})

    assert response.status_code == 200
    assert response.json()["overall"]["sample_size"] == 1


async def test_calibration_report_with_no_settled_bets_returns_none_metrics(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/calibration/report")

    assert response.status_code == 200
    body = response.json()
    assert body["overall"]["sample_size"] == 0
    assert body["overall"]["brier_score"] is None


async def test_recompute_correction_factors_persists_a_versioned_batch(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    match = _match()
    await SqlAlchemyValueBetRepository(session).save(_bet(match))
    await session.flush()
    await _settle(client, match, result="WON")

    response = await client.post("/calibration/factors/recompute")

    assert response.status_code == 200
    body = response.json()
    # A single settled bet is below the default min_sample_size (30), so no
    # segment produces a factor yet - the endpoint should still succeed.
    assert body["factors"] == []


async def test_recompute_correction_factors_returns_factors_when_enough_volume(
    client: httpx.AsyncClient, session: AsyncSession, app: FastAPI
) -> None:
    match = _match()
    await SqlAlchemyValueBetRepository(session).save(_bet(match))
    await session.flush()
    await _settle(client, match, result="WON")

    app.dependency_overrides[get_settings] = lambda: Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        ODDS_API_KEY="test-key",
        SPORTMONKS_API_TOKEN="test-token",
        CALIBRATION_MIN_SAMPLE_SIZE=1,
    )

    response = await client.post("/calibration/factors/recompute")

    assert response.status_code == 200
    factors = response.json()["factors"]
    assert len(factors) > 0
    assert factors[0]["segment_type"] == "overall"
