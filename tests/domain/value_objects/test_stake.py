import pytest

from src.domain.value_objects.stake import Stake


@pytest.mark.parametrize("amount", [0.01, 1.0, 50.5, 1000.0])
def test_valid_stake(amount: float) -> None:
    stake = Stake(amount)
    assert stake.amount == amount


@pytest.mark.parametrize("amount", [0.0, -0.01, -100.0])
def test_invalid_stake_raises_value_error(amount: float) -> None:
    with pytest.raises(ValueError):
        Stake(amount)


def test_stake_is_immutable() -> None:
    stake = Stake(10.0)
    with pytest.raises(AttributeError):
        stake.amount = 20.0  # type: ignore[misc]
