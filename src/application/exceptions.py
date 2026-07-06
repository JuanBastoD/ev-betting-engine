"""Application-layer errors - not domain invariant violations (those stay
plain `ValueError`, raised by entities/services), but orchestration-level
failures a use case hits when the data it needs isn't there.

Kept separate from `src.infrastructure.providers.exceptions.ProviderError`
(a different failure class - an upstream data source being unreachable,
not "the match/player you asked about doesn't exist").
"""


class ApplicationError(Exception):
    """Base class for all application-layer errors."""


class MatchNotFoundError(ApplicationError):
    def __init__(self, match_id: str) -> None:
        super().__init__(f"Match {match_id!r} not found")
        self.match_id = match_id


class PlayerPropNotFoundError(ApplicationError):
    """No `PlayerPropMarket` for the requested player (+ prop type) was
    found among the local bookmaker's offerings for the match."""

    def __init__(self, match_id: str, player_name: str) -> None:
        super().__init__(
            f"No player-prop market for {player_name!r} found for match {match_id!r}"
        )
        self.match_id = match_id
        self.player_name = player_name


class ValueBetNotFoundError(ApplicationError):
    """No persisted `ValueBet` matches the natural key (match + selection +
    local odds) `SettleBetUseCase` was asked to settle."""

    def __init__(self, match_id: str, outcome: str) -> None:
        super().__init__(
            f"No ValueBet found for match {match_id!r}, outcome {outcome!r} to settle"
        )
        self.match_id = match_id
        self.outcome = outcome
