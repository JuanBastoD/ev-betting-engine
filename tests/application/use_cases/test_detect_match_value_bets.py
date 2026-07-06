"""DetectMatchValueBetsUseCase tests.

Reuses the hand-verified scenario from tests/application/conftest-adjacent
fixtures: home TeamForm(goals_for=11, goals_against=9, /10) and away
TeamForm(goals_for=9, goals_against=11, /10) with league_average_goals=1.0
give TeamStrength(attack=1.1, defense=0.9)/(attack=0.9, defense=1.1) -
DixonColesModel() defaults (home_advantage=1.35, rho=-0.1) resolve those to
stat_home_win=0.557955 (breakeven 1.7923). Sharp 1X2 2.00/3.40/4.00
(multiplicative) gives market_home_win=34/71=0.478873 (breakeven 2.0882).
"""

from datetime import datetime, timezone

import pytest

from src.application.use_cases.detect_match_value_bets import DetectMatchValueBetsUseCase
from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.selection import Selection
from src.domain.entities.team import Team
from src.domain.entities.team_form import TeamForm
from src.domain.services.market_model.detector import MarketValueDetector
from src.domain.services.market_model.devig import MultiplicativeDevig
from src.domain.services.match_model.match_value_detector import ConfirmationMode, MatchValueDetector
from src.domain.services.match_model.xg_model import DixonColesModel
from src.domain.value_objects.decimal_odds import DecimalOdds
from tests.fakes import FakeValueBetRepository

SHARP = Bookmaker(name="Pinnacle", is_sharp=True, region="EU")
LOCAL = Bookmaker(name="Betplay", is_sharp=False, region="CO")
QUOTED_AT = datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc)


def _quote(match: Match, bookmaker: Bookmaker, market_type: MarketType, outcome: str, odds_value: float, *, line: float | None = None) -> OddsQuote:
    return OddsQuote(
        match=match, bookmaker=bookmaker,
        selection=Selection(market_type=market_type, outcome=outcome, line=line),
        odds=DecimalOdds(odds_value), quoted_at=QUOTED_AT,
    )


def sharp_1x2(match: Match) -> list[OddsQuote]:
    return [
        _quote(match, SHARP, MarketType.MATCH_WINNER_1X2, "Home", 2.00),
        _quote(match, SHARP, MarketType.MATCH_WINNER_1X2, "Draw", 3.40),
        _quote(match, SHARP, MarketType.MATCH_WINNER_1X2, "Away", 4.00),
    ]


@pytest.fixture
def home_form(home_team: Team) -> TeamForm:
    return TeamForm(team=home_team, matches_played=10, wins=6, draws=2, losses=2, goals_for=11, goals_against=9)


@pytest.fixture
def away_form(away_team: Team) -> TeamForm:
    return TeamForm(team=away_team, matches_played=10, wins=2, draws=2, losses=6, goals_for=9, goals_against=11)


def make_use_case(mode: ConfirmationMode = ConfirmationMode.CONFIRMATION) -> DetectMatchValueBetsUseCase:
    market_detector = MarketValueDetector(
        MultiplicativeDevig(), min_ev_threshold=0.02, kelly_fraction=0.5
    )
    match_detector = MatchValueDetector(
        DixonColesModel(), market_detector, min_ev_threshold=0.02, kelly_fraction=0.5, mode=mode
    )
    return DetectMatchValueBetsUseCase(
        match_value_detector=match_detector,
        value_bet_repository=FakeValueBetRepository(),
        league_average_goals=1.0,
    )


async def test_confirmation_mode_produces_a_both_bet_and_persists_it(
    match: Match, home_form: TeamForm, away_form: TeamForm
) -> None:
    use_case = make_use_case()
    local_quotes = [_quote(match, LOCAL, MarketType.MATCH_WINNER_1X2, "Home", 2.30)]

    value_bets = await use_case.execute(
        home_form=home_form, away_form=away_form, sharp_quotes=sharp_1x2(match), local_quotes=local_quotes
    )

    assert len(value_bets) == 1
    assert value_bets[0].model_source is ModelSource.BOTH
    assert use_case.value_bet_repository.saved == value_bets


async def test_confirmation_mode_discards_a_discrepancy(
    match: Match, home_form: TeamForm, away_form: TeamForm
) -> None:
    use_case = make_use_case()
    # Draw @ 3.60: market breakeven 3.55 (agrees), stat breakeven 3.7195 (disagrees).
    local_quotes = [_quote(match, LOCAL, MarketType.MATCH_WINNER_1X2, "Draw", 3.60)]

    value_bets = await use_case.execute(
        home_form=home_form, away_form=away_form, sharp_quotes=sharp_1x2(match), local_quotes=local_quotes
    )

    assert value_bets == []


async def test_independent_mode_produces_a_statistical_bet_without_sharp_quotes(
    match: Match, home_form: TeamForm, away_form: TeamForm
) -> None:
    use_case = make_use_case(mode=ConfirmationMode.INDEPENDENT)
    local_quotes = [_quote(match, LOCAL, MarketType.MATCH_WINNER_1X2, "Home", 2.30)]

    value_bets = await use_case.execute(
        home_form=home_form, away_form=away_form, sharp_quotes=[], local_quotes=local_quotes
    )

    assert len(value_bets) == 1
    assert value_bets[0].model_source is ModelSource.STATISTICAL


async def test_a_market_with_no_sharp_coverage_is_skipped_in_confirmation_mode(
    match: Match, home_form: TeamForm, away_form: TeamForm
) -> None:
    use_case = make_use_case()
    # Local offers BTTS, but sharp_quotes only cover 1X2 - nothing to confirm against.
    local_quotes = [_quote(match, LOCAL, MarketType.BTTS, "Yes", 1.80)]

    value_bets = await use_case.execute(
        home_form=home_form, away_form=away_form, sharp_quotes=sharp_1x2(match), local_quotes=local_quotes
    )

    assert value_bets == []


async def test_multiple_markets_are_each_detected_independently(
    match: Match, home_form: TeamForm, away_form: TeamForm
) -> None:
    use_case = make_use_case()
    sharp_quotes = [
        *sharp_1x2(match),
        _quote(match, SHARP, MarketType.OVER_UNDER, "Over", 1.90, line=2.5),
        _quote(match, SHARP, MarketType.OVER_UNDER, "Under", 1.95, line=2.5),
    ]
    local_quotes = [
        _quote(match, LOCAL, MarketType.MATCH_WINNER_1X2, "Home", 2.30),
        _quote(match, LOCAL, MarketType.OVER_UNDER, "Over", 2.30, line=2.5),
    ]

    value_bets = await use_case.execute(
        home_form=home_form, away_form=away_form, sharp_quotes=sharp_quotes, local_quotes=local_quotes
    )

    market_keys = {(vb.selection.market_type, vb.selection.line) for vb in value_bets}
    assert (MarketType.MATCH_WINNER_1X2, None) in market_keys
