"""DetectPlayerPropValueBetsUseCase tests.

Reuses Phase 8's classic vector: 3 matches @ 90 min, 2 shots on target each
-> P(Over 1.5) = 1 - 3*e^-2 = 0.593994... (breakeven ~1.6835 @ odds 1.90).
"""

import math
from datetime import datetime, timezone

from src.application.use_cases.detect_player_prop_value_bets import (
    DetectPlayerPropValueBetsUseCase,
)
from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.injury_status import InjuryStatus
from src.domain.entities.injury_status_type import InjuryStatusType
from src.domain.entities.lineup_confirmation import LineupConfirmation
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.player import Player
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.player_position import PlayerPosition
from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.entities.player_prop_type import PlayerPropType
from src.domain.entities.team import Team
from src.domain.services.player_props.player_model import PoissonPropsModel
from src.domain.services.player_props.player_prop_detector import PlayerPropDetector
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.probability import Probability
from tests.fakes import FakeValueBetRepository

LOCAL = Bookmaker(name="Betplay", is_sharp=False, region="CO")
QUOTED_AT = datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc)
MODEL_OVER_1_5 = 1.0 - 3.0 * math.exp(-2.0)


def make_use_case() -> DetectPlayerPropValueBetsUseCase:
    detector = PlayerPropDetector(PoissonPropsModel(), min_ev_threshold=0.02, kelly_fraction=0.5)
    return DetectPlayerPropValueBetsUseCase(
        player_prop_detector=detector, value_bet_repository=FakeValueBetRepository()
    )


def _prop_market(match: Match, player_name: str, *, odds_value: float = 1.90) -> PlayerPropMarket:
    return PlayerPropMarket(
        match=match, bookmaker=LOCAL, player_name=player_name,
        prop_type=PlayerPropType.SHOTS_ON_TARGET, outcome="Over", line=1.5,
        odds=DecimalOdds(odds_value), quoted_at=QUOTED_AT,
    )


def _stats(match: Match, player: Player) -> PlayerMatchStats:
    return PlayerMatchStats(
        match=match, player=player, minutes_played=90, started=True,
        shots_total=4, shots_on_target=2, goals=0, assists=0, yellow_cards=0, red_cards=0,
    )


async def test_prices_a_prop_for_a_resolvable_player_and_persists_it(
    match: Match, home_team: Team
) -> None:
    striker = Player(id="p-1", name="Carlos Bacca", team=home_team, position=PlayerPosition.FORWARD)
    lineup = [
        LineupConfirmation(
            player=striker, match=match, is_starting=True, is_confirmed=True,
            start_probability=Probability(1.0),
        )
    ]
    recent_stats = [_stats(match, striker) for _ in range(3)]
    use_case = make_use_case()

    detections = await use_case.execute(
        prop_markets=[_prop_market(match, "Carlos Bacca")],
        recent_stats_by_player_id={striker.id: recent_stats},
        lineup_confirmations=lineup,
        injury_statuses=[],
    )

    assert len(detections) == 1
    bet = detections[0].value_bet
    assert bet.model_source is ModelSource.STATISTICAL
    assert bet.lineup_confirmed is True
    assert bet.fair_probability.value == MODEL_OVER_1_5
    assert use_case.value_bet_repository.saved == [bet]


async def test_player_name_matching_is_case_insensitive(match: Match, home_team: Team) -> None:
    striker = Player(id="p-1", name="Carlos Bacca", team=home_team, position=PlayerPosition.FORWARD)
    lineup = [
        LineupConfirmation(
            player=striker, match=match, is_starting=True, is_confirmed=True,
            start_probability=Probability(1.0),
        )
    ]
    recent_stats = [_stats(match, striker) for _ in range(3)]
    use_case = make_use_case()

    detections = await use_case.execute(
        prop_markets=[_prop_market(match, "carlos bacca")],  # different casing than the Player's name
        recent_stats_by_player_id={striker.id: recent_stats},
        lineup_confirmations=lineup,
        injury_statuses=[],
    )

    assert len(detections) == 1


async def test_a_prop_for_an_unresolvable_player_is_skipped_not_an_error(match: Match) -> None:
    use_case = make_use_case()

    detections = await use_case.execute(
        prop_markets=[_prop_market(match, "Nobody We Have Data On")],
        recent_stats_by_player_id={},
        lineup_confirmations=[],
        injury_statuses=[],
    )

    assert detections == []


async def test_an_injured_player_still_resolves_but_prices_lower(match: Match, home_team: Team) -> None:
    striker = Player(id="p-1", name="Carlos Bacca", team=home_team, position=PlayerPosition.FORWARD)
    injuries = [
        InjuryStatus(
            player=striker, status=InjuryStatusType.DOUBTFUL, source="test", updated_at=QUOTED_AT
        )
    ]
    recent_stats = [_stats(match, striker) for _ in range(3)]
    use_case = make_use_case()

    detections = await use_case.execute(
        prop_markets=[_prop_market(match, "Carlos Bacca")],
        recent_stats_by_player_id={striker.id: recent_stats},
        lineup_confirmations=[],
        injury_statuses=injuries,
    )

    assert len(detections) == 1
    assert detections[0].value_bet.fair_probability.value < MODEL_OVER_1_5


async def test_below_threshold_props_are_not_persisted(match: Match, home_team: Team) -> None:
    striker = Player(id="p-1", name="Carlos Bacca", team=home_team, position=PlayerPosition.FORWARD)
    lineup = [
        LineupConfirmation(
            player=striker, match=match, is_starting=True, is_confirmed=True,
            start_probability=Probability(1.0),
        )
    ]
    recent_stats = [_stats(match, striker) for _ in range(3)]
    use_case = make_use_case()
    # Breakeven for MODEL_OVER_1_5 is ~1.6835; 1.65 is below it -> negative edge.
    detections = await use_case.execute(
        prop_markets=[_prop_market(match, "Carlos Bacca", odds_value=1.65)],
        recent_stats_by_player_id={striker.id: recent_stats},
        lineup_confirmations=lineup,
        injury_statuses=[],
    )

    assert detections == []
    assert use_case.value_bet_repository.saved == []
