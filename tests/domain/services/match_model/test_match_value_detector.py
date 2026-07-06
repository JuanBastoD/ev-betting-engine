"""MatchValueDetector orchestration tests.

Scenario setup shared across most tests: sharp 1X2 Pinnacle odds
2.00/3.40/4.00 (the same hand-derived vector used throughout
test_devig.py/test_detector.py) give multiplicative fair probabilities
Home=34/71=0.478873..., Draw=20/71=0.281690..., Away=17/71=0.239437...
(breakeven odds 2.0882/3.55/4.1765). The statistical side uses
TeamStrength(attack=1.1/0.9, defense=0.9/1.1) with home_advantage=1.3,
rho=-0.1, league_average_goals=1.4, which DixonColesModel resolves to
home_win=0.607045 (breakeven 1.6473), draw=0.215686, away_win=0.177270
(breakeven 5.6414) - verified once via the model itself and pinned here as
literals, since re-deriving Dixon-Coles by hand is already covered
exhaustively in test_xg_model.py; this file's job is the confirmation/
blending/mode-switching orchestration, not the xG math.

Stat's Home breakeven (1.6473) sits *below* market's (2.0882), so odds
between them (e.g. 1.80) satisfy the statistical model but not the market -
letting one test cover the "only stat agrees" branch. Away's breakevens sit
in the opposite order (market 4.1765 < stat 5.6414), covering "only market
agrees" with the same sharp_quotes/strengths setup.
"""

from collections.abc import Callable
from types import SimpleNamespace

import pytest

from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.team import Team
from src.domain.services.market_model.detector import MarketValueDetector
from src.domain.services.market_model.devig import MultiplicativeDevig
from src.domain.services.match_model.match_value_detector import (
    ConfirmationMode,
    MatchValueDetector,
    _statistical_probability_for,
)
from src.domain.services.match_model.team_strength import TeamStrength
from src.domain.services.match_model.xg_model import DixonColesModel

STAT_HOME_WIN = 0.6070447285834996
STAT_DRAW = 0.2156856948951963
STAT_AWAY_WIN = 0.1772695765213041
MARKET_HOME_WIN = 34 / 71
MARKET_AWAY_WIN = 17 / 71


def make_market_detector(**overrides: object) -> MarketValueDetector:
    kwargs: dict = dict(
        devig_strategy=MultiplicativeDevig(), min_ev_threshold=0.02, kelly_fraction=0.25
    )
    kwargs.update(overrides)
    return MarketValueDetector(**kwargs)


def make_detector(**overrides: object) -> MatchValueDetector:
    kwargs: dict = dict(
        statistical_model=DixonColesModel(home_advantage=1.3, rho=-0.1),
        market_detector=make_market_detector(),
        min_ev_threshold=0.02,
        kelly_fraction=0.25,
    )
    kwargs.update(overrides)
    return MatchValueDetector(**kwargs)


@pytest.fixture
def home_strength(home_team: Team) -> TeamStrength:
    return TeamStrength(team=home_team, attack=1.1, defense=0.9)


@pytest.fixture
def away_strength(away_team: Team) -> TeamStrength:
    return TeamStrength(team=away_team, attack=0.9, defense=1.1)


def sharp_1x2(
    match: Match, sharp_bookmaker: object, make_quote: Callable[..., OddsQuote]
) -> list[OddsQuote]:
    return [
        make_quote(match, sharp_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 2.00),
        make_quote(match, sharp_bookmaker, MarketType.MATCH_WINNER_1X2, "Draw", 3.40),
        make_quote(match, sharp_bookmaker, MarketType.MATCH_WINNER_1X2, "Away", 4.00),
    ]


def detect_kwargs(
    home_strength: TeamStrength, away_strength: TeamStrength, **overrides: object
) -> dict:
    kwargs: dict = dict(
        home_strength=home_strength, away_strength=away_strength, league_average_goals=1.4
    )
    kwargs.update(overrides)
    return kwargs


# --- CONFIRMATION mode (default) ----------------------------------------------


def test_mode_property_reflects_the_constructor_argument() -> None:
    assert make_detector(mode=ConfirmationMode.CONFIRMATION).mode is ConfirmationMode.CONFIRMATION
    assert make_detector(mode=ConfirmationMode.INDEPENDENT).mode is ConfirmationMode.INDEPENDENT


def test_confirmation_mode_generates_a_value_bet_when_both_sources_agree(
    match: Match,
    sharp_bookmaker: object,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    # Home @ 2.30 clears both breakevens (market 2.0882, stat 1.6473).
    local_quotes = [make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 2.30)]

    value_bets = make_detector().detect(
        **detect_kwargs(home_strength, away_strength, sharp_quotes=sharp_quotes, local_quotes=local_quotes)
    )

    assert len(value_bets) == 1
    bet = value_bets[0]
    assert bet.model_source is ModelSource.BOTH
    expected_blend = 0.5 * MARKET_HOME_WIN + 0.5 * STAT_HOME_WIN
    assert bet.fair_probability.value == pytest.approx(expected_blend)
    assert bet.edge.value == pytest.approx((expected_blend * 2.30 - 1) * 100)
    assert bet.suggested_stake.amount > 0.0
    assert bet.bookmaker is local_bookmaker


def test_confirmation_mode_skips_when_only_the_market_agrees(
    match: Match,
    sharp_bookmaker: object,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    # Away @ 4.50: market breakeven 4.1765 (agrees), stat breakeven 5.6414 (disagrees).
    local_quotes = [make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Away", 4.50)]

    value_bets = make_detector().detect(
        **detect_kwargs(home_strength, away_strength, sharp_quotes=sharp_quotes, local_quotes=local_quotes)
    )

    assert value_bets == []


def test_confirmation_mode_skips_when_only_the_statistical_model_agrees(
    match: Match,
    sharp_bookmaker: object,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    # Home @ 1.80: stat breakeven 1.6473 (agrees), market breakeven 2.0882 (disagrees).
    local_quotes = [make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 1.80)]

    value_bets = make_detector().detect(
        **detect_kwargs(home_strength, away_strength, sharp_quotes=sharp_quotes, local_quotes=local_quotes)
    )

    assert value_bets == []


def test_confirmation_mode_requires_sharp_quotes(
    match: Match,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    local_quotes = [make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 2.30)]

    with pytest.raises(ValueError, match="sharp_quotes"):
        make_detector().detect(
            **detect_kwargs(home_strength, away_strength, sharp_quotes=None, local_quotes=local_quotes)
        )


def test_market_weight_controls_the_blend(
    match: Match,
    sharp_bookmaker: object,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    local_quotes = [make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 2.30)]

    heavy_market = make_detector(market_weight=0.8).detect(
        **detect_kwargs(home_strength, away_strength, sharp_quotes=sharp_quotes, local_quotes=local_quotes)
    )
    heavy_stat = make_detector(market_weight=0.2).detect(
        **detect_kwargs(home_strength, away_strength, sharp_quotes=sharp_quotes, local_quotes=local_quotes)
    )

    assert heavy_market[0].fair_probability.value == pytest.approx(
        0.8 * MARKET_HOME_WIN + 0.2 * STAT_HOME_WIN
    )
    assert heavy_stat[0].fair_probability.value == pytest.approx(
        0.2 * MARKET_HOME_WIN + 0.8 * STAT_HOME_WIN
    )


@pytest.mark.parametrize("market_weight", [-0.1, 1.1])
def test_market_weight_out_of_range_raises(market_weight: float) -> None:
    with pytest.raises(ValueError):
        make_detector(market_weight=market_weight)


def test_mismatched_match_on_local_quote_raises(
    match: Match,
    home_team: Team,
    away_team: Team,
    league: object,
    sharp_bookmaker: object,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    from datetime import datetime, timezone

    other_match = Match(
        id="match-2",
        home_team=home_team,
        away_team=away_team,
        league=league,
        kickoff_utc=datetime(2026, 8, 16, 20, 0, tzinfo=timezone.utc),
    )
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    local_quotes = [
        make_quote(other_match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 2.30)
    ]

    with pytest.raises(ValueError):
        make_detector().detect(
            **detect_kwargs(home_strength, away_strength, sharp_quotes=sharp_quotes, local_quotes=local_quotes)
        )


def test_outcome_the_sharp_side_never_quoted_raises(
    match: Match,
    sharp_bookmaker: object,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    local_quotes = [
        make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Nobody", 2.30)
    ]

    with pytest.raises(ValueError, match="outcome"):
        make_detector().detect(
            **detect_kwargs(home_strength, away_strength, sharp_quotes=sharp_quotes, local_quotes=local_quotes)
        )


def test_over_under_line_the_model_was_not_configured_for_raises(
    match: Match,
    sharp_bookmaker: object,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    sharp_quotes = [
        make_quote(match, sharp_bookmaker, MarketType.OVER_UNDER, "Over", 1.90, line=6.5),
        make_quote(match, sharp_bookmaker, MarketType.OVER_UNDER, "Under", 1.95, line=6.5),
    ]
    local_quotes = [
        make_quote(match, local_bookmaker, MarketType.OVER_UNDER, "Over", 2.00, line=6.5)
    ]

    with pytest.raises(ValueError):
        make_detector().detect(
            **detect_kwargs(home_strength, away_strength, sharp_quotes=sharp_quotes, local_quotes=local_quotes)
        )


def test_min_ev_threshold_applies_to_the_blended_probability(
    match: Match,
    sharp_bookmaker: object,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    local_quotes = [make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 2.30)]

    value_bets = make_detector(min_ev_threshold=0.5).detect(
        **detect_kwargs(home_strength, away_strength, sharp_quotes=sharp_quotes, local_quotes=local_quotes)
    )

    assert value_bets == []


# --- INDEPENDENT mode -----------------------------------------------------------


def test_independent_mode_ignores_the_market_entirely(
    match: Match,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    # Home @ 1.80: only the statistical model would approve this (market
    # breakeven is 2.0882) - independent mode doesn't need sharp_quotes at all.
    local_quotes = [make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 1.80)]

    value_bets = make_detector(mode=ConfirmationMode.INDEPENDENT).detect(
        **detect_kwargs(
            home_strength, away_strength, sharp_quotes=None, local_quotes=local_quotes
        )
    )

    assert len(value_bets) == 1
    bet = value_bets[0]
    assert bet.model_source is ModelSource.STATISTICAL
    assert bet.fair_probability.value == pytest.approx(STAT_HOME_WIN)
    assert bet.edge.value == pytest.approx((STAT_HOME_WIN * 1.80 - 1) * 100)
    assert bet.bookmaker is local_bookmaker


def test_independent_mode_still_filters_by_ev_threshold(
    match: Match,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    # Home @ exactly the statistical breakeven -> ~0% edge, below threshold.
    breakeven = 1.0 / STAT_HOME_WIN
    local_quotes = [
        make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", breakeven)
    ]

    value_bets = make_detector(mode=ConfirmationMode.INDEPENDENT).detect(
        **detect_kwargs(
            home_strength, away_strength, sharp_quotes=None, local_quotes=local_quotes
        )
    )

    assert value_bets == []


def test_independent_mode_ignores_sharp_quotes_even_if_provided(
    match: Match,
    sharp_bookmaker: object,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    local_quotes = [make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 1.80)]

    value_bets = make_detector(mode=ConfirmationMode.INDEPENDENT).detect(
        **detect_kwargs(
            home_strength, away_strength, sharp_quotes=sharp_quotes, local_quotes=local_quotes
        )
    )

    assert len(value_bets) == 1
    assert value_bets[0].model_source is ModelSource.STATISTICAL
    assert value_bets[0].fair_probability.value == pytest.approx(STAT_HOME_WIN)


def test_independent_mode_prices_btts_directly_from_the_model(
    match: Match,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    local_quotes = [
        make_quote(match, local_bookmaker, MarketType.BTTS, "Yes", 10.0),
        make_quote(match, local_bookmaker, MarketType.BTTS, "No", 10.0),
    ]

    value_bets = make_detector(mode=ConfirmationMode.INDEPENDENT).detect(
        **detect_kwargs(home_strength, away_strength, sharp_quotes=None, local_quotes=local_quotes)
    )

    assert {bet.selection.outcome for bet in value_bets} == {"Yes", "No"}


def test_independent_mode_prices_over_under_directly_from_the_model(
    match: Match,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    local_quotes = [
        make_quote(match, local_bookmaker, MarketType.OVER_UNDER, "Over", 10.0, line=2.5),
        make_quote(match, local_bookmaker, MarketType.OVER_UNDER, "Under", 10.0, line=2.5),
    ]

    value_bets = make_detector(mode=ConfirmationMode.INDEPENDENT).detect(
        **detect_kwargs(home_strength, away_strength, sharp_quotes=None, local_quotes=local_quotes)
    )

    assert {bet.selection.outcome for bet in value_bets} == {"Over", "Under"}


def test_confirmation_mode_skips_when_kelly_fraction_is_zero_even_if_both_sources_agree(
    match: Match,
    sharp_bookmaker: object,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    local_quotes = [make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 2.30)]

    value_bets = make_detector(kelly_fraction=0.0).detect(
        **detect_kwargs(home_strength, away_strength, sharp_quotes=sharp_quotes, local_quotes=local_quotes)
    )

    assert value_bets == []


def test_independent_mode_prices_draw_and_away_directly_from_the_model(
    match: Match,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
    home_strength: TeamStrength,
    away_strength: TeamStrength,
) -> None:
    local_quotes = [
        make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Draw", 10.0),
        make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Away", 10.0),
    ]

    value_bets = make_detector(mode=ConfirmationMode.INDEPENDENT).detect(
        **detect_kwargs(
            home_strength, away_strength, sharp_quotes=None, local_quotes=local_quotes
        )
    )

    by_outcome = {bet.selection.outcome: bet for bet in value_bets}
    assert by_outcome["Draw"].fair_probability.value == pytest.approx(STAT_DRAW)
    assert by_outcome["Away"].fair_probability.value == pytest.approx(STAT_AWAY_WIN)


# --- _statistical_probability_for: unsupported selections ----------------------


def _probabilities(home_strength: TeamStrength, away_strength: TeamStrength) -> object:
    return DixonColesModel(home_advantage=1.3, rho=-0.1).predict_match_probabilities(
        home_strength, away_strength, league_average_goals=1.4
    )


def test_unsupported_1x2_outcome_raises(
    home_strength: TeamStrength, away_strength: TeamStrength
) -> None:
    probabilities = _probabilities(home_strength, away_strength)
    selection = SimpleNamespace(market_type=MarketType.MATCH_WINNER_1X2, outcome="Nobody", line=None)

    with pytest.raises(ValueError, match="1X2 outcome"):
        _statistical_probability_for(selection, probabilities)


def test_unsupported_btts_outcome_raises(
    home_strength: TeamStrength, away_strength: TeamStrength
) -> None:
    probabilities = _probabilities(home_strength, away_strength)
    selection = SimpleNamespace(market_type=MarketType.BTTS, outcome="Maybe", line=None)

    with pytest.raises(ValueError, match="BTTS outcome"):
        _statistical_probability_for(selection, probabilities)


def test_unsupported_over_under_outcome_raises(
    home_strength: TeamStrength, away_strength: TeamStrength
) -> None:
    probabilities = _probabilities(home_strength, away_strength)
    selection = SimpleNamespace(market_type=MarketType.OVER_UNDER, outcome="Exactly", line=2.5)

    with pytest.raises(ValueError, match="Over/Under outcome"):
        _statistical_probability_for(selection, probabilities)


def test_unsupported_market_type_raises(
    home_strength: TeamStrength, away_strength: TeamStrength
) -> None:
    """No current MarketType member reaches this branch - it guards against
    a future market type (e.g. corners/cards) being added without updating
    this pricing function. A duck-typed fake selection exercises it."""
    probabilities = _probabilities(home_strength, away_strength)
    selection = SimpleNamespace(market_type="CORNERS", outcome="Over", line=9.5)

    with pytest.raises(ValueError, match="Unsupported market type"):
        _statistical_probability_for(selection, probabilities)
