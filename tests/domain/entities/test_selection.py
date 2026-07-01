import pytest

from src.domain.entities.market_type import MarketType
from src.domain.entities.selection import Selection


def test_valid_selection_without_line() -> None:
    selection = Selection(market_type=MarketType.BTTS, outcome="Yes")
    assert selection.market_type is MarketType.BTTS
    assert selection.outcome == "Yes"
    assert selection.line is None


def test_valid_selection_with_line() -> None:
    selection = Selection(market_type=MarketType.OVER_UNDER, outcome="Over", line=2.5)
    assert selection.line == 2.5


def test_selection_requires_non_empty_outcome() -> None:
    with pytest.raises(ValueError):
        Selection(market_type=MarketType.MATCH_WINNER_1X2, outcome="")
