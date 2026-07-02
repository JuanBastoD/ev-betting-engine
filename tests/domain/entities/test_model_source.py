from src.domain.entities.model_source import ModelSource


def test_model_source_members() -> None:
    assert ModelSource.MARKET == "MARKET"
    assert ModelSource.MATCH_STATS == "MATCH_STATS"
    assert ModelSource.PLAYER_PROPS == "PLAYER_PROPS"


def test_model_source_is_str_enum() -> None:
    assert isinstance(ModelSource.MARKET, str)
