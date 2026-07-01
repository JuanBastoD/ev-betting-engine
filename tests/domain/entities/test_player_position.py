from src.domain.entities.player_position import PlayerPosition


def test_player_position_members() -> None:
    assert PlayerPosition.GOALKEEPER == "GOALKEEPER"
    assert PlayerPosition.DEFENDER == "DEFENDER"
    assert PlayerPosition.MIDFIELDER == "MIDFIELDER"
    assert PlayerPosition.FORWARD == "FORWARD"
    assert PlayerPosition.UNKNOWN == "UNKNOWN"


def test_player_position_is_str_enum() -> None:
    assert isinstance(PlayerPosition.FORWARD, str)
