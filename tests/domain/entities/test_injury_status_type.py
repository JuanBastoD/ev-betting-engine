from src.domain.entities.injury_status_type import InjuryStatusType


def test_injury_status_type_members() -> None:
    assert InjuryStatusType.FIT == "FIT"
    assert InjuryStatusType.DOUBTFUL == "DOUBTFUL"
    assert InjuryStatusType.INJURED == "INJURED"
    assert InjuryStatusType.SUSPENDED == "SUSPENDED"


def test_injury_status_type_is_str_enum() -> None:
    assert isinstance(InjuryStatusType.INJURED, str)
