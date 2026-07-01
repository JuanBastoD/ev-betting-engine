import pytest

from src.domain.entities.team import Team


def test_valid_team_construction() -> None:
    team = Team(id="team-1", name="River Plate", country="Argentina")
    assert team.id == "team-1"
    assert team.name == "River Plate"
    assert team.country == "Argentina"


def test_team_country_is_optional() -> None:
    team = Team(id="team-1", name="River Plate")
    assert team.country is None


@pytest.mark.parametrize(("id_", "name"), [("", "River Plate"), ("team-1", "")])
def test_team_requires_non_empty_id_and_name(id_: str, name: str) -> None:
    with pytest.raises(ValueError):
        Team(id=id_, name=name)
