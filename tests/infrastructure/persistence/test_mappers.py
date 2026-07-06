from datetime import datetime, timezone

import pytest

from src.domain.entities.bet_result import BetResult
from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.league import League
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.model_source import ModelSource
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.player import Player
from src.domain.entities.player_match_stats import PlayerMatchStats
from src.domain.entities.selection import Selection
from src.domain.entities.settled_bet import SettledBet
from src.domain.entities.team import Team
from src.domain.entities.team_form import TeamForm
from src.domain.entities.value_bet import ValueBet
from src.domain.services.calibration.correction_factor import CorrectionFactor
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.edge_percentage import EdgePercentage
from src.domain.value_objects.probability import Probability
from src.domain.value_objects.stake import Stake
from src.infrastructure.persistence.mappers import (
    bookmaker_from_model,
    bookmaker_to_model,
    correction_factor_from_model,
    correction_factor_to_model,
    league_from_model,
    league_to_model,
    match_from_model,
    match_to_model,
    odds_quote_from_model,
    odds_quote_to_model,
    player_from_model,
    player_match_stats_from_model,
    player_match_stats_to_model,
    player_to_model,
    settled_bet_from_model,
    settled_bet_to_model,
    team_form_from_model,
    team_form_to_model,
    team_from_model,
    team_to_model,
    value_bet_from_model,
    value_bet_to_model,
)


def test_team_round_trip(home_team: Team) -> None:
    restored = team_from_model(team_to_model(home_team))
    assert restored == home_team


def test_team_round_trip_without_country() -> None:
    team = Team(id="team-x", name="Independiente")
    restored = team_from_model(team_to_model(team))
    assert restored == team


def test_league_round_trip(league: League) -> None:
    restored = league_from_model(league_to_model(league))
    assert restored == league


def test_bookmaker_round_trip(bookmaker: Bookmaker) -> None:
    restored = bookmaker_from_model(bookmaker_to_model(bookmaker))
    assert restored == bookmaker


def test_match_round_trip(match: Match, home_team: Team, away_team: Team, league: League) -> None:
    model = match_to_model(match)
    model.home_team = team_to_model(home_team)
    model.away_team = team_to_model(away_team)
    model.league = league_to_model(league)

    restored = match_from_model(model)

    assert restored == match


@pytest.mark.parametrize(
    ("market_type", "outcome", "line"),
    [
        (MarketType.MATCH_WINNER_1X2, "Home", None),
        (MarketType.OVER_UNDER, "Over", 2.5),
        (MarketType.BTTS, "Yes", None),
    ],
)
def test_odds_quote_round_trip(
    match: Match,
    home_team: Team,
    away_team: Team,
    league: League,
    bookmaker: Bookmaker,
    market_type: MarketType,
    outcome: str,
    line: float | None,
) -> None:
    odds_quote = OddsQuote(
        match=match,
        bookmaker=bookmaker,
        selection=Selection(market_type=market_type, outcome=outcome, line=line),
        odds=DecimalOdds(1.95),
        quoted_at=datetime(2026, 8, 15, 19, 0, tzinfo=timezone.utc),
    )

    model = odds_quote_to_model(odds_quote, bookmaker_id=1)
    assert model.match_id == match.id
    model.bookmaker = bookmaker_to_model(bookmaker)
    match_model = match_to_model(match)
    match_model.home_team = team_to_model(home_team)
    match_model.away_team = team_to_model(away_team)
    match_model.league = league_to_model(league)
    model.match = match_model

    restored = odds_quote_from_model(model)

    assert restored == odds_quote


def test_team_form_round_trip(home_team: Team) -> None:
    team_form = TeamForm(
        team=home_team,
        matches_played=10,
        wins=6,
        draws=2,
        losses=2,
        goals_for=18,
        goals_against=9,
    )

    model = team_form_to_model(team_form)
    model.team = team_to_model(home_team)

    restored = team_form_from_model(model)

    assert restored == team_form


@pytest.mark.parametrize("lineup_confirmed", [None, True, False])
def test_value_bet_round_trip(
    match: Match,
    home_team: Team,
    away_team: Team,
    league: League,
    selection: Selection,
    lineup_confirmed: bool | None,
) -> None:
    value_bet = ValueBet(
        match=match,
        selection=selection,
        local_odds=DecimalOdds(2.20),
        fair_probability=Probability(0.5),
        edge=EdgePercentage(10.0),
        suggested_stake=Stake(25.0),
        model_source=ModelSource.MARKET,
        lineup_confirmed=lineup_confirmed,
    )

    model = value_bet_to_model(value_bet)
    assert model.model_source == "MARKET"
    match_model = match_to_model(match)
    match_model.home_team = team_to_model(home_team)
    match_model.away_team = team_to_model(away_team)
    match_model.league = league_to_model(league)
    model.match = match_model

    restored = value_bet_from_model(model)

    assert restored == value_bet


def test_value_bet_round_trip_with_bookmaker(
    match: Match, home_team: Team, away_team: Team, league: League, selection: Selection, bookmaker: Bookmaker
) -> None:
    value_bet = ValueBet(
        match=match,
        selection=selection,
        local_odds=DecimalOdds(2.20),
        fair_probability=Probability(0.5),
        edge=EdgePercentage(10.0),
        suggested_stake=Stake(25.0),
        model_source=ModelSource.MARKET,
        bookmaker=bookmaker,
    )

    model = value_bet_to_model(value_bet, bookmaker_id=1)
    match_model = match_to_model(match)
    match_model.home_team = team_to_model(home_team)
    match_model.away_team = team_to_model(away_team)
    match_model.league = league_to_model(league)
    model.match = match_model
    model.bookmaker = bookmaker_to_model(bookmaker)

    restored = value_bet_from_model(model)

    assert restored == value_bet


def test_player_round_trip(player: Player, home_team: Team) -> None:
    model = player_to_model(player)
    model.team = team_to_model(home_team)

    restored = player_from_model(model)

    assert restored == player


def test_player_match_stats_round_trip(
    match: Match, home_team: Team, away_team: Team, league: League, player: Player
) -> None:
    stats = PlayerMatchStats(
        match=match,
        player=player,
        minutes_played=90,
        started=True,
        shots_total=4,
        shots_on_target=2,
        goals=1,
        assists=1,
        yellow_cards=1,
        red_cards=0,
        corners_won=3,
    )

    model = player_match_stats_to_model(stats)
    match_model = match_to_model(match)
    match_model.home_team = team_to_model(home_team)
    match_model.away_team = team_to_model(away_team)
    match_model.league = league_to_model(league)
    model.match = match_model
    player_model = player_to_model(player)
    player_model.team = team_to_model(home_team)
    model.player = player_model

    restored = player_match_stats_from_model(model)

    assert restored == stats


def test_player_match_stats_round_trip_without_corners_won(
    match: Match, home_team: Team, away_team: Team, league: League, player: Player
) -> None:
    stats = PlayerMatchStats(
        match=match,
        player=player,
        minutes_played=15,
        started=False,
        shots_total=1,
        shots_on_target=0,
        goals=0,
        assists=0,
        yellow_cards=0,
        red_cards=0,
    )

    model = player_match_stats_to_model(stats)
    match_model = match_to_model(match)
    match_model.home_team = team_to_model(home_team)
    match_model.away_team = team_to_model(away_team)
    match_model.league = league_to_model(league)
    model.match = match_model
    player_model = player_to_model(player)
    player_model.team = team_to_model(home_team)
    model.player = player_model

    restored = player_match_stats_from_model(model)

    assert restored == stats
    assert restored.corners_won is None


def _value_bet(match: Match, selection: Selection, bookmaker: Bookmaker | None = None) -> ValueBet:
    return ValueBet(
        match=match,
        selection=selection,
        local_odds=DecimalOdds(2.20),
        fair_probability=Probability(0.5),
        edge=EdgePercentage(10.0),
        suggested_stake=Stake(25.0),
        model_source=ModelSource.MARKET,
        bookmaker=bookmaker,
    )


@pytest.mark.parametrize(
    ("result", "closing_sharp_odds"),
    [(BetResult.WON, 2.00), (BetResult.LOST, None), (BetResult.PUSH, 2.20)],
)
def test_settled_bet_round_trip(
    match: Match,
    home_team: Team,
    away_team: Team,
    league: League,
    selection: Selection,
    bookmaker: Bookmaker,
    result: BetResult,
    closing_sharp_odds: float | None,
) -> None:
    settled_bet = SettledBet(
        value_bet=_value_bet(match, selection, bookmaker=bookmaker),
        result=result,
        settled_at=datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc),
        closing_sharp_odds=DecimalOdds(closing_sharp_odds) if closing_sharp_odds else None,
    )

    model = settled_bet_to_model(settled_bet, bookmaker_id=1)
    match_model = match_to_model(match)
    match_model.home_team = team_to_model(home_team)
    match_model.away_team = team_to_model(away_team)
    match_model.league = league_to_model(league)
    model.match = match_model
    model.bookmaker = bookmaker_to_model(bookmaker)

    restored = settled_bet_from_model(model)

    assert restored == settled_bet


def test_settled_bet_round_trip_without_bookmaker(
    match: Match, home_team: Team, away_team: Team, league: League, selection: Selection
) -> None:
    settled_bet = SettledBet(
        value_bet=_value_bet(match, selection),
        result=BetResult.WON,
        settled_at=datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc),
    )

    model = settled_bet_to_model(settled_bet)
    match_model = match_to_model(match)
    match_model.home_team = team_to_model(home_team)
    match_model.away_team = team_to_model(away_team)
    match_model.league = league_to_model(league)
    model.match = match_model

    restored = settled_bet_from_model(model)

    assert restored == settled_bet
    assert restored.value_bet.bookmaker is None


def test_correction_factor_round_trip() -> None:
    correction_factor = CorrectionFactor(
        segment_type="market_type",
        segment_value="PLAYER_PROP",
        factor=0.92,
        sample_size=150,
        computed_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        data_range_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        data_range_end=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )

    model = correction_factor_to_model(correction_factor)
    restored = correction_factor_from_model(model)

    assert restored == correction_factor
