import pytest

from src.domain.entities.league import League


def test_valid_league_construction() -> None:
    league = League(id="league-1", name="Liga Profesional", country="Argentina")
    assert league.id == "league-1"
    assert league.name == "Liga Profesional"
    assert league.country == "Argentina"


def test_league_country_is_optional() -> None:
    league = League(id="league-1", name="Liga Profesional")
    assert league.country is None


@pytest.mark.parametrize(("id_", "name"), [("", "Liga Profesional"), ("league-1", "")])
def test_league_requires_non_empty_id_and_name(id_: str, name: str) -> None:
    with pytest.raises(ValueError):
        League(id=id_, name=name)
