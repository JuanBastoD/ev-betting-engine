from enum import Enum


class ModelSource(str, Enum):
    """Which probability model (or combination) produced a ValueBet.

    MARKET: fair probability from de-vigged sharp (Pinnacle) odds alone.
    STATISTICAL: fair probability from a team-form/xG statistical model alone
    (independent mode - no requirement that the market agrees).
    BOTH: market and statistical model both independently found positive
    edge above the threshold (double-confirmation mode) - the persisted
    fair_probability is their weighted blend.
    PLAYER_PROPS: reserved for the future player-prop model.
    """

    MARKET = "MARKET"
    STATISTICAL = "STATISTICAL"
    BOTH = "BOTH"
    PLAYER_PROPS = "PLAYER_PROPS"
