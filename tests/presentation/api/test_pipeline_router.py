"""POST /pipeline/run and POST /value-bets/query tests.

Same hand-verified scenario as tests/application/use_cases/test_run_pipeline.py:
sharp 1X2 2.00/3.40/4.00, TeamForm giving TeamStrength 1.1/0.9 and 0.9/1.1 at
league_average_goals=1.0 (set via `test_settings` in conftest.py), local Home
@ 2.30 (BOTH bet), local Draw @ 3.60 (discrepancy, discarded), a player prop
(Carlos Bacca Over 1.5 SOT @ 1.90, confirmed starter, 3x90min/2 SOT history).
"""

from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.league import League
from src.domain.entities.lineup_confirmation import LineupConfirmation
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.player import Player
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_position import PlayerPosition
from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.entities.player_prop_type import PlayerPropType
from src.domain.entities.selection import Selection
from src.domain.entities.team import Team
from src.domain.entities.team_form import TeamForm
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.probability import Probability
from tests.fakes import (
    FakeLocalOddsProvider,
    FakePlayerStatsProvider,
    FakeSharpOddsProvider,
    FakeStatsProvider,
)

SHARP = Bookmaker(name="Pinnacle", is_sharp=True, region="EU")
LOCAL = Bookmaker(name="Betplay", is_sharp=False, region="CO")
QUOTED_AT = datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc)


def _quote(match: Match, bookmaker: Bookmaker, outcome: str, odds_value: float) -> OddsQuote:
    return OddsQuote(
        match=match, bookmaker=bookmaker,
        selection=Selection(market_type=MarketType.MATCH_WINNER_1X2, outcome=outcome),
        odds=DecimalOdds(odds_value), quoted_at=QUOTED_AT,
    )


@pytest.fixture
def home_team() -> Team:
    return Team(id="team-home", name="River Plate")


@pytest.fixture
def away_team() -> Team:
    return Team(id="team-away", name="Boca Juniors")


@pytest.fixture
def match(home_team: Team, away_team: Team) -> Match:
    return Match(
        id="match-1", home_team=home_team, away_team=away_team,
        league=League(id="league-1", name="Liga Profesional"),
        kickoff_utc=datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def striker(home_team: Team) -> Player:
    return Player(id="p-striker", name="Carlos Bacca", team=home_team, position=PlayerPosition.FORWARD)


@pytest.fixture(autouse=True)
def _seed_fakes(
    match: Match,
    home_team: Team,
    away_team: Team,
    striker: Player,
    fake_sharp_odds_provider: FakeSharpOddsProvider,
    fake_stats_provider: FakeStatsProvider,
    fake_local_odds_provider: FakeLocalOddsProvider,
    fake_player_stats_provider: FakePlayerStatsProvider,
) -> None:
    fake_sharp_odds_provider._quotes_by_match_id[match.id] = [
        _quote(match, SHARP, "Home", 2.00), _quote(match, SHARP, "Draw", 3.40), _quote(match, SHARP, "Away", 4.00),
    ]
    fake_stats_provider._forms_by_team_id[home_team.id] = TeamForm(
        team=home_team, matches_played=10, wins=6, draws=2, losses=2, goals_for=11, goals_against=9
    )
    fake_stats_provider._forms_by_team_id[away_team.id] = TeamForm(
        team=away_team, matches_played=10, wins=2, draws=2, losses=6, goals_for=9, goals_against=11
    )
    fake_local_odds_provider._quotes_by_match_id[match.id] = [
        _quote(match, LOCAL, "Home", 2.30), _quote(match, LOCAL, "Draw", 3.60),
    ]
    prop_market = PlayerPropMarket(
        match=match, bookmaker=LOCAL, player_name="Carlos Bacca", prop_type=PlayerPropType.SHOTS_ON_TARGET,
        outcome="Over", line=1.5, odds=DecimalOdds(1.90), quoted_at=QUOTED_AT,
    )
    fake_local_odds_provider._props_by_match_id[match.id] = [prop_market]

    recent_stats = [
        PlayerMatchStats(
            match=match, player=striker, minutes_played=90, started=True,
            shots_total=4, shots_on_target=2, goals=0, assists=0, yellow_cards=0, red_cards=0,
        )
        for _ in range(3)
    ]
    fake_player_stats_provider._recent_matches_by_player_id[striker.id] = recent_stats
    fake_player_stats_provider._lineups_by_match_id[match.id] = [
        LineupConfirmation(
            player=striker, match=match, is_starting=True, is_confirmed=True,
            start_probability=Probability(1.0),
        )
    ]


async def test_pipeline_run_reports_matches_processed_and_breakdown(
    client: httpx.AsyncClient, match: Match, session: AsyncSession
) -> None:
    await _save_match(session, match)

    response = await client.post("/pipeline/run")

    assert response.status_code == 200
    body = response.json()
    assert body["matches_processed"] == 1
    assert body["total_value_bets"] == 2  # one BOTH match bet + one prop bet
    assert body["value_bets_by_market_type"]["MATCH_WINNER_1X2"] == 1
    assert body["value_bets_by_market_type"]["PLAYER_PROP"] == 1
    assert body["value_bets_by_model_source"]["BOTH"] == 1
    assert body["value_bets_by_model_source"]["STATISTICAL"] == 1


async def _save_match(session: AsyncSession, match: Match) -> None:
    from src.infrastructure.persistence.repositories.match_repository import (
        SqlAlchemyMatchRepository,
    )

    await SqlAlchemyMatchRepository(session).save(match)
    await session.flush()


async def test_pipeline_run_with_no_upcoming_matches_processes_zero(client: httpx.AsyncClient) -> None:
    response = await client.post("/pipeline/run")

    assert response.status_code == 200
    body = response.json()
    assert body["matches_processed"] == 0
    assert body["total_value_bets"] == 0


async def test_query_runs_the_pipeline_for_just_that_match(
    client: httpx.AsyncClient, match: Match, session: AsyncSession
) -> None:
    await _save_match(session, match)

    response = await client.post("/value-bets/query", json={"match_id": match.id})

    assert response.status_code == 200
    body = response.json()
    assert body["match_id"] == match.id
    assert len(body["value_bets"]) == 2


async def test_query_filters_by_player_name(
    client: httpx.AsyncClient, match: Match, session: AsyncSession
) -> None:
    await _save_match(session, match)

    response = await client.post(
        "/value-bets/query", json={"match_id": match.id, "player_name": "Carlos Bacca"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["value_bets"]) == 1
    assert body["value_bets"][0]["market_type"] == "PLAYER_PROP"


async def test_query_filters_by_prop_type(
    client: httpx.AsyncClient, match: Match, session: AsyncSession
) -> None:
    await _save_match(session, match)

    response = await client.post(
        "/value-bets/query", json={"match_id": match.id, "prop_type": "SHOTS_ON_TARGET"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["value_bets"]) == 1
    assert body["value_bets"][0]["market_type"] == "PLAYER_PROP"


async def test_query_filters_by_prop_type_that_matches_nothing(
    client: httpx.AsyncClient, match: Match, session: AsyncSession
) -> None:
    await _save_match(session, match)

    response = await client.post(
        "/value-bets/query", json={"match_id": match.id, "prop_type": "CARDS"}
    )

    assert response.status_code == 200
    assert response.json()["value_bets"] == []


async def test_query_filters_by_player_name_that_matches_nothing(
    client: httpx.AsyncClient, match: Match, session: AsyncSession
) -> None:
    await _save_match(session, match)

    response = await client.post(
        "/value-bets/query", json={"match_id": match.id, "player_name": "Nobody Real"}
    )

    assert response.status_code == 200
    assert response.json()["value_bets"] == []


async def test_query_for_an_unknown_match_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.post("/value-bets/query", json={"match_id": "no-such-match"})

    assert response.status_code == 404
    assert "no-such-match" in response.json()["detail"]
