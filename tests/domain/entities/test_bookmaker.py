import pytest

from src.domain.entities.bookmaker import Bookmaker


def test_valid_bookmaker_construction() -> None:
    bookmaker = Bookmaker(name="Pinnacle", is_sharp=True, region="EU")
    assert bookmaker.name == "Pinnacle"
    assert bookmaker.is_sharp is True
    assert bookmaker.region == "EU"


@pytest.mark.parametrize(("name", "region"), [("", "EU"), ("Pinnacle", "")])
def test_bookmaker_requires_non_empty_name_and_region(name: str, region: str) -> None:
    with pytest.raises(ValueError):
        Bookmaker(name=name, is_sharp=False, region=region)
