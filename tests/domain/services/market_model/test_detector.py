"""MarketValueDetector orchestration tests.

Reuses the hand-derived asymmetric vector from test_devig.py: Pinnacle 1X2
odds 2.00/3.40/4.00 -> multiplicative fair probabilities 34/71 (Home),
20/71 (Draw), 17/71 (Away). Breakeven odds are 71/34=2.0882... (Home),
71/20=3.55 (Draw), 71/17=4.1765... (Away).
"""

from collections.abc import Callable

import pytest

from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.odds_quote import OddsQuote
from src.domain.services.market_model.detector import MarketValueDetector
from src.domain.services.market_model.devig import AdditiveDevig, MultiplicativeDevig


def make_detector(**overrides: object) -> MarketValueDetector:
    kwargs: dict = dict(
        devig_strategy=MultiplicativeDevig(), min_ev_threshold=0.02, kelly_fraction=0.25
    )
    kwargs.update(overrides)
    return MarketValueDetector(**kwargs)


def sharp_1x2(
    match: Match, sharp_bookmaker: object, make_quote: Callable[..., OddsQuote]
) -> list[OddsQuote]:
    return [
        make_quote(match, sharp_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 2.00),
        make_quote(match, sharp_bookmaker, MarketType.MATCH_WINNER_1X2, "Draw", 3.40),
        make_quote(match, sharp_bookmaker, MarketType.MATCH_WINNER_1X2, "Away", 4.00),
    ]


def test_detects_a_single_plus_ev_selection_and_ignores_the_rest(
    match: Match, sharp_bookmaker: object, local_bookmaker: object, make_quote: Callable[..., OddsQuote]
) -> None:
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    local_quotes = [
        # Home: breakeven 2.0882..., local 2.30 clearly beats it -> +EV.
        make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 2.30),
        # Draw: breakeven 3.55, local 3.40 is worse -> -EV.
        make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Draw", 3.40),
        # Away: breakeven 4.1765..., local exactly at breakeven -> 0% edge.
        make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Away", 71 / 17),
    ]

    value_bets = make_detector().detect(sharp_quotes, local_quotes)

    assert len(value_bets) == 1
    bet = value_bets[0]
    assert bet.match == match
    assert bet.selection.outcome == "Home"
    assert bet.local_odds.value == pytest.approx(2.30)
    assert bet.fair_probability.value == pytest.approx(34 / 71)
    assert bet.edge.value == pytest.approx(((34 / 71) * 2.30 - 1) * 100)
    assert bet.edge.is_positive_ev is True
    assert bet.model_source is ModelSource.MARKET
    assert bet.suggested_stake.amount > 0.0
    assert bet.bookmaker is local_bookmaker


def test_min_ev_threshold_excludes_edges_below_the_bar(
    match: Match, sharp_bookmaker: object, local_bookmaker: object, make_quote: Callable[..., OddsQuote]
) -> None:
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    # Home breakeven is 2.0882...; 2.10 clears it but only by ~0.6% edge,
    # below a 5% minimum threshold.
    local_quotes = [make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 2.10)]

    value_bets = make_detector(min_ev_threshold=0.05).detect(sharp_quotes, local_quotes)

    assert value_bets == []


def test_multiple_bookmakers_on_the_same_outcome_each_produce_a_value_bet(
    match: Match, sharp_bookmaker: object, local_bookmaker: object, make_quote: Callable[..., OddsQuote]
) -> None:
    from src.domain.entities.bookmaker import Bookmaker

    other_local = Bookmaker(name="Stake", is_sharp=False, region="CO")
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    local_quotes = [
        make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 2.30),
        make_quote(match, other_local, MarketType.MATCH_WINNER_1X2, "Home", 2.35),
    ]

    value_bets = make_detector().detect(sharp_quotes, local_quotes)

    assert len(value_bets) == 2
    assert {bet.local_odds.value for bet in value_bets} == {2.30, 2.35}


def test_devig_strategy_is_injected_not_hardcoded(
    match: Match, sharp_bookmaker: object, local_bookmaker: object, make_quote: Callable[..., OddsQuote]
) -> None:
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    local_quotes = [make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 2.30)]

    multiplicative_bets = make_detector(devig_strategy=MultiplicativeDevig()).detect(
        sharp_quotes, local_quotes
    )
    additive_bets = make_detector(devig_strategy=AdditiveDevig()).detect(sharp_quotes, local_quotes)

    assert multiplicative_bets[0].fair_probability.value == pytest.approx(34 / 71)
    assert additive_bets[0].fair_probability.value == pytest.approx(33 / 68)
    assert multiplicative_bets[0].fair_probability.value != additive_bets[0].fair_probability.value


def test_kelly_fraction_of_zero_disables_staking_even_for_a_plus_ev_selection(
    match: Match, sharp_bookmaker: object, local_bookmaker: object, make_quote: Callable[..., OddsQuote]
) -> None:
    """kelly_fraction=0.0 is a legitimate "staking suggestions off" config,
    not a bug: it must suppress every ValueBet even when EV is clearly
    positive, since kelly_stake always returns None once the sizing factor
    is zero."""
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    local_quotes = [make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 2.30)]

    value_bets = make_detector(kelly_fraction=0.0).detect(sharp_quotes, local_quotes)

    assert value_bets == []


def test_empty_sharp_quotes_raises(local_bookmaker: object) -> None:
    with pytest.raises(ValueError):
        make_detector().detect([], [])


def test_local_quote_for_a_different_match_raises(
    match: Match,
    home_team: object,
    away_team: object,
    league: object,
    sharp_bookmaker: object,
    local_bookmaker: object,
    make_quote: Callable[..., OddsQuote],
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

    with pytest.raises(ValueError, match="match"):
        make_detector().detect(sharp_quotes, local_quotes)


def test_sharp_quotes_spanning_different_markets_raises(
    match: Match, sharp_bookmaker: object, make_quote: Callable[..., OddsQuote]
) -> None:
    sharp_quotes = [
        make_quote(match, sharp_bookmaker, MarketType.MATCH_WINNER_1X2, "Home", 2.00),
        make_quote(match, sharp_bookmaker, MarketType.OVER_UNDER, "Over", 1.95, line=2.5),
    ]

    with pytest.raises(ValueError, match="market"):
        make_detector().detect(sharp_quotes, [])


def test_local_quote_for_a_different_market_raises(
    match: Match, sharp_bookmaker: object, local_bookmaker: object, make_quote: Callable[..., OddsQuote]
) -> None:
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    local_quotes = [
        make_quote(match, local_bookmaker, MarketType.OVER_UNDER, "Over", 1.95, line=2.5)
    ]

    with pytest.raises(ValueError, match="market"):
        make_detector().detect(sharp_quotes, local_quotes)


def test_local_quote_for_an_outcome_the_sharp_side_never_quoted_raises(
    match: Match, sharp_bookmaker: object, local_bookmaker: object, make_quote: Callable[..., OddsQuote]
) -> None:
    sharp_quotes = sharp_1x2(match, sharp_bookmaker, make_quote)
    local_quotes = [
        make_quote(match, local_bookmaker, MarketType.MATCH_WINNER_1X2, "Nobody", 2.30)
    ]

    with pytest.raises(ValueError, match="outcome"):
        make_detector().detect(sharp_quotes, local_quotes)


def test_over_under_market_uses_line_as_part_of_the_market_key(
    match: Match, sharp_bookmaker: object, local_bookmaker: object, make_quote: Callable[..., OddsQuote]
) -> None:
    sharp_quotes = [
        make_quote(match, sharp_bookmaker, MarketType.OVER_UNDER, "Over", 1.90, line=2.5),
        make_quote(match, sharp_bookmaker, MarketType.OVER_UNDER, "Under", 1.95, line=2.5),
    ]
    local_quotes = [
        make_quote(match, local_bookmaker, MarketType.OVER_UNDER, "Over", 2.10, line=2.5)
    ]

    value_bets = make_detector(min_ev_threshold=0.0).detect(sharp_quotes, local_quotes)

    assert len(value_bets) == 1
    assert value_bets[0].selection.line == 2.5
