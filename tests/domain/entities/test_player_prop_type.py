from src.domain.entities.player_prop_type import PlayerPropType


def test_player_prop_type_members() -> None:
    assert PlayerPropType.GOALS == "GOALS"
    assert PlayerPropType.SHOTS_ON_TARGET == "SHOTS_ON_TARGET"
    assert PlayerPropType.ASSISTS == "ASSISTS"
    assert PlayerPropType.CARDS == "CARDS"


def test_player_prop_type_is_str_enum() -> None:
    assert isinstance(PlayerPropType.GOALS, str)
