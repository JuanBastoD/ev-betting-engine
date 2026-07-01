import pytest

from src.domain.value_objects.probability import Probability


@pytest.mark.parametrize("value", [0.0, 0.0001, 0.5, 0.9999, 1.0])
def test_valid_probability(value: float) -> None:
    probability = Probability(value)
    assert probability.value == value


@pytest.mark.parametrize("value", [-0.0001, -1.0, 1.0001, 2.0])
def test_invalid_probability_raises_value_error(value: float) -> None:
    with pytest.raises(ValueError):
        Probability(value)


def test_probability_is_immutable() -> None:
    probability = Probability(0.5)
    with pytest.raises(AttributeError):
        probability.value = 0.9  # type: ignore[misc]
