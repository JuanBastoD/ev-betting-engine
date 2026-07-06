"""PlayerPropDetector orchestration tests.

Shared scenario: a player averaging 2.0 shots on target per 90 (3 matches,
constant rate, so EWMA doesn't matter here), confirmed starter, FIT ->
model_probability for Over 1.5 = 1 - 3*e^-2 = 0.593994... Breakeven odds =
1/0.593994... = 1.6835... Local odds 1.90 clears it comfortably.
"""

import math
from collections.abc import Callable

import pytest

from src.domain.entities.injury_status import InjuryStatus
from src.domain.entities.injury_status_type import InjuryStatusType
from src.domain.entities.lineup_confirmation import LineupConfirmation
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.player import Player
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.entities.player_prop_type import PlayerPropType
from src.domain.services.player_props.player_model import PoissonPropsModel
from src.domain.services.player_props.player_prop_detector import PlayerPropDetector
from src.domain.value_objects.probability import Probability

MODEL_OVER_1_5 = 1.0 - 3.0 * math.exp(-2.0)


def make_detector(**overrides: object) -> PlayerPropDetector:
    kwargs: dict = dict(
        model=PoissonPropsModel(), min_ev_threshold=0.02, kelly_fraction=0.25
    )
    kwargs.update(overrides)
    return PlayerPropDetector(**kwargs)


@pytest.fixture
def historical_stats(make_stats: Callable[..., PlayerMatchStats]) -> list[PlayerMatchStats]:
    return [make_stats(minutes_played=90, shots_on_target=2) for _ in range(3)]


@pytest.fixture
def confirmed_starter(match: Match, player: Player) -> LineupConfirmation:
    return LineupConfirmation(
        player=player, match=match, is_starting=True, is_confirmed=True,
        start_probability=Probability(1.0),
    )


def test_detects_a_plus_ev_prop_with_confirmed_lineup(
    make_prop_market: Callable[..., PlayerPropMarket],
    historical_stats: list[PlayerMatchStats],
    confirmed_starter: LineupConfirmation,
) -> None:
    prop_market = make_prop_market(odds_value=1.90)

    detection = make_detector().detect(
        prop_market=prop_market, historical_stats=historical_stats,
        lineup_confirmation=confirmed_starter,
    )

    assert detection is not None
    assert detection.lineup_confirmed is True
    assert detection.confidence == pytest.approx(1.0)

    bet = detection.value_bet
    assert bet.match is prop_market.match
    assert bet.selection.market_type is MarketType.PLAYER_PROP
    assert bet.selection.line == 1.5
    assert prop_market.player_name in bet.selection.outcome
    assert prop_market.prop_type.value in bet.selection.outcome
    assert bet.local_odds.value == pytest.approx(1.90)
    assert bet.fair_probability.value == pytest.approx(MODEL_OVER_1_5)
    assert bet.edge.value == pytest.approx((MODEL_OVER_1_5 * 1.90 - 1) * 100)
    assert bet.model_source is ModelSource.STATISTICAL
    assert bet.suggested_stake.amount > 0.0
    assert bet.bookmaker is prop_market.bookmaker


def test_returns_none_when_below_the_ev_threshold(
    make_prop_market: Callable[..., PlayerPropMarket],
    historical_stats: list[PlayerMatchStats],
    confirmed_starter: LineupConfirmation,
) -> None:
    # Breakeven for MODEL_OVER_1_5 is ~1.6835; 1.70 clears it by <1%.
    prop_market = make_prop_market(odds_value=1.70)

    detection = make_detector(min_ev_threshold=0.05).detect(
        prop_market=prop_market, historical_stats=historical_stats,
        lineup_confirmation=confirmed_starter,
    )

    assert detection is None


def test_unconfirmed_lineup_reduces_the_effective_probability_and_is_reported(
    make_prop_market: Callable[..., PlayerPropMarket],
    historical_stats: list[PlayerMatchStats],
    match: Match,
    player: Player,
) -> None:
    prop_market = make_prop_market(odds_value=1.90)
    unconfirmed = LineupConfirmation(
        player=player, match=match, is_starting=True, is_confirmed=False,
        start_probability=Probability(0.9),
    )

    confirmed_detection = make_detector(min_ev_threshold=0.0).detect(
        prop_market=prop_market, historical_stats=historical_stats,
        lineup_confirmation=LineupConfirmation(
            player=player, match=match, is_starting=True, is_confirmed=True,
            start_probability=Probability(1.0),
        ),
    )
    unconfirmed_detection = make_detector(min_ev_threshold=0.0, unconfirmed_lineup_penalty=0.5).detect(
        prop_market=prop_market, historical_stats=historical_stats,
        lineup_confirmation=unconfirmed,
    )

    assert unconfirmed_detection is not None
    assert unconfirmed_detection.lineup_confirmed is False
    assert unconfirmed_detection.confidence == pytest.approx(0.5)
    assert confirmed_detection is not None
    assert unconfirmed_detection.value_bet.edge.value < confirmed_detection.value_bet.edge.value


def test_no_lineup_confirmation_at_all_is_treated_as_unconfirmed(
    make_prop_market: Callable[..., PlayerPropMarket],
    historical_stats: list[PlayerMatchStats],
) -> None:
    prop_market = make_prop_market(odds_value=1.90)

    detection = make_detector(unconfirmed_lineup_penalty=0.5).detect(
        prop_market=prop_market, historical_stats=historical_stats, lineup_confirmation=None,
    )

    assert detection is not None
    assert detection.lineup_confirmed is False
    assert detection.confidence == pytest.approx(0.5)
    # expected_minutes still defaults to a full match (assumed, not penalized there).
    assert detection.value_bet.fair_probability.value < MODEL_OVER_1_5


@pytest.mark.parametrize(
    "status", [InjuryStatusType.DOUBTFUL, InjuryStatusType.INJURED, InjuryStatusType.SUSPENDED]
)
def test_doubtful_or_injured_status_reduces_confidence(
    make_prop_market: Callable[..., PlayerPropMarket],
    historical_stats: list[PlayerMatchStats],
    confirmed_starter: LineupConfirmation,
    player: Player,
    status: InjuryStatusType,
) -> None:
    prop_market = make_prop_market(odds_value=1.90)
    injury = InjuryStatus(
        player=player, status=status, source="test",
        updated_at=confirmed_starter.match.kickoff_utc,
    )

    detection = make_detector(doubtful_or_injured_penalty=0.4).detect(
        prop_market=prop_market, historical_stats=historical_stats,
        lineup_confirmation=confirmed_starter, injury_status=injury,
    )

    assert detection is not None
    assert detection.confidence == pytest.approx(0.6)


def test_fit_status_is_not_penalized(
    make_prop_market: Callable[..., PlayerPropMarket],
    historical_stats: list[PlayerMatchStats],
    confirmed_starter: LineupConfirmation,
    player: Player,
) -> None:
    prop_market = make_prop_market(odds_value=1.90)
    injury = InjuryStatus(
        player=player, status=InjuryStatusType.FIT, source="test",
        updated_at=confirmed_starter.match.kickoff_utc,
    )

    detection = make_detector().detect(
        prop_market=prop_market, historical_stats=historical_stats,
        lineup_confirmation=confirmed_starter, injury_status=injury,
    )

    assert detection is not None
    assert detection.confidence == pytest.approx(1.0)


def test_no_injury_status_at_all_assumes_fit(
    make_prop_market: Callable[..., PlayerPropMarket],
    historical_stats: list[PlayerMatchStats],
    confirmed_starter: LineupConfirmation,
) -> None:
    prop_market = make_prop_market(odds_value=1.90)

    detection = make_detector().detect(
        prop_market=prop_market, historical_stats=historical_stats,
        lineup_confirmation=confirmed_starter, injury_status=None,
    )

    assert detection is not None
    assert detection.confidence == pytest.approx(1.0)


def test_opponent_strength_factor_is_forwarded_to_the_model(
    make_prop_market: Callable[..., PlayerPropMarket],
    historical_stats: list[PlayerMatchStats],
    confirmed_starter: LineupConfirmation,
) -> None:
    prop_market = make_prop_market(odds_value=1.90)

    baseline = make_detector().detect(
        prop_market=prop_market, historical_stats=historical_stats,
        lineup_confirmation=confirmed_starter,
    )
    boosted = make_detector().detect(
        prop_market=prop_market, historical_stats=historical_stats,
        lineup_confirmation=confirmed_starter, opponent_strength_factor=1.5,
    )

    assert baseline is not None
    assert boosted is not None
    assert boosted.value_bet.fair_probability.value > baseline.value_bet.fair_probability.value


def test_kelly_fraction_of_zero_returns_none_even_with_positive_edge(
    make_prop_market: Callable[..., PlayerPropMarket],
    historical_stats: list[PlayerMatchStats],
    confirmed_starter: LineupConfirmation,
) -> None:
    prop_market = make_prop_market(odds_value=1.90)

    detection = make_detector(kelly_fraction=0.0).detect(
        prop_market=prop_market, historical_stats=historical_stats,
        lineup_confirmation=confirmed_starter,
    )

    assert detection is None


def test_lineless_prop_market_raises(
    make_prop_market: Callable[..., PlayerPropMarket],
    historical_stats: list[PlayerMatchStats],
    confirmed_starter: LineupConfirmation,
) -> None:
    prop_market = make_prop_market(line=None, outcome="Yes")

    with pytest.raises(ValueError, match="line-based"):
        make_detector().detect(
            prop_market=prop_market, historical_stats=historical_stats,
            lineup_confirmation=confirmed_starter,
        )


def test_selection_outcome_encodes_player_prop_type_and_outcome(
    make_prop_market: Callable[..., PlayerPropMarket],
    historical_stats: list[PlayerMatchStats],
    confirmed_starter: LineupConfirmation,
) -> None:
    prop_market = make_prop_market(
        player_name="Luis Diaz", prop_type=PlayerPropType.SHOTS_ON_TARGET, outcome="Over",
    )

    detection = make_detector().detect(
        prop_market=prop_market, historical_stats=historical_stats,
        lineup_confirmation=confirmed_starter,
    )

    assert detection is not None
    assert detection.value_bet.selection.outcome == "Luis Diaz SHOTS_ON_TARGET Over"
