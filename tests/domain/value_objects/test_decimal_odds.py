import pytest

from src.domain.value_objects.decimal_odds import DecimalOdds


@pytest.mark.parametrize("value", [1.01, 1.5, 2.10, 10.0, 1000.0])
def test_valid_decimal_odds(value: float) -> None:
    odds = DecimalOdds(value)
    assert odds.value == value


@pytest.mark.parametrize("value", [1.0, 0.99, 0.0, -1.5])
def test_invalid_decimal_odds_raises_value_error(value: float) -> None:
    with pytest.raises(ValueError):
        DecimalOdds(value)


def test_decimal_odds_is_immutable() -> None:
    odds = DecimalOdds(2.0)
    with pytest.raises(AttributeError):
        odds.value = 3.0  # type: ignore[misc]


def test_decimal_odds_implied_probability() -> None:
    odds = DecimalOdds(2.0)
    assert odds.implied_probability == pytest.approx(0.5)
