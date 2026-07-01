import pytest

from src.domain.value_objects.edge_percentage import EdgePercentage


@pytest.mark.parametrize("value", [-100.0, -50.0, 0.0, 4.5, 250.0])
def test_valid_edge_percentage(value: float) -> None:
    edge = EdgePercentage(value)
    assert edge.value == value


@pytest.mark.parametrize("value", [-100.01, -101.0, -1000.0])
def test_invalid_edge_percentage_raises_value_error(value: float) -> None:
    with pytest.raises(ValueError):
        EdgePercentage(value)


def test_edge_percentage_is_immutable() -> None:
    edge = EdgePercentage(5.0)
    with pytest.raises(AttributeError):
        edge.value = 10.0  # type: ignore[misc]


@pytest.mark.parametrize(("value", "expected"), [(0.01, True), (0.0, False), (-5.0, False)])
def test_edge_percentage_is_positive_ev(value: float, expected: bool) -> None:
    assert EdgePercentage(value).is_positive_ev is expected
