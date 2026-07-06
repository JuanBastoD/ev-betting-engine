"""RunPipelineUseCase (Facade) end-to-end test, entirely with in-memory
fakes (tests/fakes.py) - no network, no browser, no real DB.

Reuses the same hand-verified numbers as test_detect_match_value_bets.py
(sharp 1X2 2.00/3.40/4.00, TeamForm giving TeamStrength attack/defense
1.1/0.9 and 0.9/1.1 at league_average_goals=1.0 -> stat_home_win breakeven
1.7923, market_home_win breakeven 2.0882) and test_detect_player_prop_value_bets.py
(3x90min/2 SOT -> P(Over 1.5)=0.593994..., breakeven ~1.6835).

Produces, in one pipeline pass:
- a MATCH bet with model_source=BOTH (Home @ 2.30 - both market and stat agree)
- a discarded discrepancy (Draw @ 3.60 - market agrees, stat doesn't -> no bet)
- a PLAYER_PROP bet with model_source=STATISTICAL (Carlos Bacca Over 1.5 SOT @ 1.90)
"""

from datetime import datetime, timezone

import pytest

from src.application.use_cases.detect_match_value_bets import DetectMatchValueBetsUseCase
from src.application.use_cases.detect_player_prop_value_bets import (
    DetectPlayerPropValueBetsUseCase,
)
from src.application.use_cases.ingest_local_odds import IngestLocalOddsUseCase
from src.application.use_cases.ingest_player_stats import IngestPlayerStatsUseCase
from src.application.use_cases.ingest_sharp_odds import IngestSharpOddsUseCase
from src.application.use_cases.run_pipeline import RunPipelineUseCase
from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.lineup_confirmation import LineupConfirmation
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.player import Player
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_position import PlayerPosition
from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.entities.player_prop_type import PlayerPropType
from src.domain.entities.selection import Selection
from src.domain.entities.team import Team
from src.domain.entities.team_form import TeamForm
from src.domain.services.market_model.detector import MarketValueDetector
from src.domain.services.market_model.devig import MultiplicativeDevig
from src.domain.services.match_model.match_value_detector import ConfirmationMode, MatchValueDetector
from src.domain.services.match_model.xg_model import DixonColesModel
from src.domain.services.player_props.player_model import PoissonPropsModel
from src.domain.services.player_props.player_prop_detector import PlayerPropDetector
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.probability import Probability
from tests.fakes import (
    FakeLocalOddsProvider,
    FakeMatchRepository,
    FakeOddsRepository,
    FakePlayerRepository,
    FakePlayerStatsProvider,
    FakePlayerStatsRepository,
    FakeSharpOddsProvider,
    FakeStatsProvider,
    FakeValueBetRepository,
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


def _prop_stats(match: Match, player: Player) -> PlayerMatchStats:
    return PlayerMatchStats(
        match=match, player=player, minutes_played=90, started=True,
        shots_total=4, shots_on_target=2, goals=0, assists=0, yellow_cards=0, red_cards=0,
    )


@pytest.fixture
def striker(home_team: Team) -> Player:
    return Player(id="p-striker", name="Carlos Bacca", team=home_team, position=PlayerPosition.FORWARD)


def build_pipeline(
    match: Match,
    home_team: Team,
    away_team: Team,
    striker: Player,
    *,
    mode: ConfirmationMode = ConfirmationMode.CONFIRMATION,
) -> RunPipelineUseCase:
    home_form = TeamForm(team=home_team, matches_played=10, wins=6, draws=2, losses=2, goals_for=11, goals_against=9)
    away_form = TeamForm(team=away_team, matches_played=10, wins=2, draws=2, losses=6, goals_for=9, goals_against=11)

    sharp_odds_provider = FakeSharpOddsProvider(
        {match.id: [_quote(match, SHARP, "Home", 2.00), _quote(match, SHARP, "Draw", 3.40), _quote(match, SHARP, "Away", 4.00)]}
    )
    stats_provider = FakeStatsProvider({home_team.id: home_form, away_team.id: away_form})
    match_repository = FakeMatchRepository()
    odds_repository = FakeOddsRepository()

    prop_market = PlayerPropMarket(
        match=match, bookmaker=LOCAL, player_name="Carlos Bacca", prop_type=PlayerPropType.SHOTS_ON_TARGET,
        outcome="Over", line=1.5, odds=DecimalOdds(1.90), quoted_at=QUOTED_AT,
    )
    local_odds_provider = FakeLocalOddsProvider(
        quotes_by_match_id={
            match.id: [
                _quote(match, LOCAL, "Home", 2.30),
                _quote(match, LOCAL, "Draw", 3.60),
            ]
        },
        props_by_match_id={match.id: [prop_market]},
    )

    lineup = [
        LineupConfirmation(
            player=striker, match=match, is_starting=True, is_confirmed=True,
            start_probability=Probability(1.0),
        )
    ]
    player_stats_provider = FakePlayerStatsProvider(
        recent_matches_by_player_id={striker.id: [_prop_stats(match, striker) for _ in range(3)]},
        lineups_by_match_id={match.id: lineup},
    )
    player_repository = FakePlayerRepository()
    player_stats_repository = FakePlayerStatsRepository()

    value_bet_repository = FakeValueBetRepository()

    market_detector = MarketValueDetector(MultiplicativeDevig(), min_ev_threshold=0.02, kelly_fraction=0.5)
    match_detector = MatchValueDetector(
        DixonColesModel(), market_detector, min_ev_threshold=0.02, kelly_fraction=0.5, mode=mode
    )
    prop_detector = PlayerPropDetector(PoissonPropsModel(), min_ev_threshold=0.02, kelly_fraction=0.5)

    return RunPipelineUseCase(
        match_repository=match_repository,
        ingest_sharp_odds=IngestSharpOddsUseCase(
            sharp_odds_provider=sharp_odds_provider, stats_provider=stats_provider,
            match_repository=match_repository, odds_repository=odds_repository,
        ),
        ingest_local_odds=IngestLocalOddsUseCase(
            local_odds_provider=local_odds_provider, odds_repository=odds_repository
        ),
        ingest_player_stats=IngestPlayerStatsUseCase(
            player_stats_provider=player_stats_provider, player_repository=player_repository,
            player_stats_repository=player_stats_repository,
        ),
        detect_match_value_bets=DetectMatchValueBetsUseCase(
            match_value_detector=match_detector, value_bet_repository=value_bet_repository,
            league_average_goals=1.0,
        ),
        detect_player_prop_value_bets=DetectPlayerPropValueBetsUseCase(
            player_prop_detector=prop_detector, value_bet_repository=value_bet_repository,
        ),
    )


async def test_pipeline_produces_a_confirmed_match_bet_and_a_player_prop_bet(
    match: Match, home_team: Team, away_team: Team, striker: Player
) -> None:
    pipeline = build_pipeline(match, home_team, away_team, striker)

    result = await pipeline.execute(matches=[match])

    assert result.matches_processed == 1
    assert len(result.match_value_bets) == 1
    assert result.match_value_bets[0].model_source is ModelSource.BOTH
    assert result.match_value_bets[0].selection.outcome == "Home"

    assert len(result.player_prop_value_bets) == 1
    prop_bet = result.player_prop_value_bets[0]
    assert prop_bet.model_source is ModelSource.STATISTICAL
    assert prop_bet.selection.market_type is MarketType.PLAYER_PROP
    assert prop_bet.lineup_confirmed is True


async def test_confirmation_mode_discards_the_draw_discrepancy(
    match: Match, home_team: Team, away_team: Team, striker: Player
) -> None:
    pipeline = build_pipeline(match, home_team, away_team, striker)

    result = await pipeline.execute(matches=[match])

    outcomes = {vb.selection.outcome for vb in result.match_value_bets}
    assert "Draw" not in outcomes  # market agrees (breakeven 3.55 < 3.60) but stat disagrees (3.7195 > 3.60)


async def test_independent_mode_produces_a_statistical_match_bet_instead(
    match: Match, home_team: Team, away_team: Team, striker: Player
) -> None:
    pipeline = build_pipeline(match, home_team, away_team, striker, mode=ConfirmationMode.INDEPENDENT)

    result = await pipeline.execute(matches=[match])

    assert len(result.match_value_bets) >= 1
    assert all(vb.model_source is ModelSource.STATISTICAL for vb in result.match_value_bets)


async def test_pipeline_persists_every_detected_value_bet(
    match: Match, home_team: Team, away_team: Team, striker: Player
) -> None:
    pipeline = build_pipeline(match, home_team, away_team, striker)

    result = await pipeline.execute(matches=[match])

    saved = pipeline.detect_match_value_bets.value_bet_repository.saved
    assert set(id(vb) for vb in saved) == {
        id(vb) for vb in [*result.match_value_bets, *result.player_prop_value_bets]
    }


async def test_execute_with_no_matches_argument_uses_list_upcoming(
    match: Match, home_team: Team, away_team: Team, striker: Player
) -> None:
    pipeline = build_pipeline(match, home_team, away_team, striker)
    await pipeline.match_repository.save(match)

    result = await pipeline.execute()

    assert result.matches_processed == 1


async def test_execute_with_zero_matches_returns_zero_counts(
    home_team: Team, away_team: Team, striker: Player, match: Match
) -> None:
    pipeline = build_pipeline(match, home_team, away_team, striker)

    result = await pipeline.execute(matches=[])

    assert result.matches_processed == 0
    assert result.match_value_bets == []
    assert result.player_prop_value_bets == []
