from src.domain.entities.bet_result import BetResult


def test_bet_result_has_expected_members() -> None:
    assert BetResult.WON.value == "WON"
    assert BetResult.LOST.value == "LOST"
    assert BetResult.PUSH.value == "PUSH"


def test_bet_result_is_constructible_from_its_value() -> None:
    assert BetResult("WON") is BetResult.WON
