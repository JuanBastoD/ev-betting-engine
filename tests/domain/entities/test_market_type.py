from src.domain.entities.market_type import MarketType


def test_market_type_members() -> None:
    assert MarketType.MATCH_WINNER_1X2 == "MATCH_WINNER_1X2"
    assert MarketType.OVER_UNDER == "OVER_UNDER"
    assert MarketType.BTTS == "BTTS"


def test_market_type_is_str_enum() -> None:
    assert isinstance(MarketType.BTTS, str)
