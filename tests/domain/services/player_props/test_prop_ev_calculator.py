from collections.abc import Callable

import pytest

from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.services.player_props.prop_ev_calculator import calculate_ev, calculate_prop_ev
from src.domain.value_objects.probability import Probability


def test_calculate_prop_ev_matches_calculate_ev_against_the_market_odds(
    make_prop_market: Callable[..., PlayerPropMarket],
) -> None:
    prop_market = make_prop_market(odds_value=2.20)

    edge = calculate_prop_ev(fair_probability=Probability(0.5), prop_market=prop_market)

    assert edge.value == pytest.approx(
        calculate_ev(fair_probability=Probability(0.5), local_odds=prop_market.odds).value
    )
    assert edge.value == pytest.approx(10.0)
