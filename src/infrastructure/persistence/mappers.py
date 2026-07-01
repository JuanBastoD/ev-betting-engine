"""Explicit Entity <-> ORM Model conversion (Data Mapper pattern).

This is the only place that is allowed to know about both the domain
(src.domain) and SQLAlchemy models (models.py). The domain never imports
from here.
"""

from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.league import League
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.selection import Selection
from src.domain.entities.team import Team
from src.domain.entities.team_form import TeamForm
from src.domain.entities.value_bet import ValueBet
from src.domain.value_objects.decimal_odds import DecimalOdds
from src.domain.value_objects.edge_percentage import EdgePercentage
from src.domain.value_objects.probability import Probability
from src.domain.value_objects.stake import Stake
from src.infrastructure.persistence.models import (
    BookmakerModel,
    LeagueModel,
    MatchModel,
    OddsQuoteModel,
    TeamFormModel,
    TeamModel,
    ValueBetModel,
)


def team_to_model(team: Team) -> TeamModel:
    return TeamModel(id=team.id, name=team.name, country=team.country)


def team_from_model(model: TeamModel) -> Team:
    return Team(id=model.id, name=model.name, country=model.country)


def league_to_model(league: League) -> LeagueModel:
    return LeagueModel(id=league.id, name=league.name, country=league.country)


def league_from_model(model: LeagueModel) -> League:
    return League(id=model.id, name=model.name, country=model.country)


def bookmaker_to_model(bookmaker: Bookmaker) -> BookmakerModel:
    return BookmakerModel(name=bookmaker.name, is_sharp=bookmaker.is_sharp, region=bookmaker.region)


def bookmaker_from_model(model: BookmakerModel) -> Bookmaker:
    return Bookmaker(name=model.name, is_sharp=model.is_sharp, region=model.region)


def match_to_model(match: Match) -> MatchModel:
    return MatchModel(
        id=match.id,
        home_team_id=match.home_team.id,
        away_team_id=match.away_team.id,
        league_id=match.league.id,
        kickoff_utc=match.kickoff_utc,
    )


def match_from_model(model: MatchModel) -> Match:
    return Match(
        id=model.id,
        home_team=team_from_model(model.home_team),
        away_team=team_from_model(model.away_team),
        league=league_from_model(model.league),
        kickoff_utc=model.kickoff_utc,
    )


def _selection_to_columns(selection: Selection) -> dict[str, str | float | None]:
    return {
        "market_type": selection.market_type.value,
        "outcome": selection.outcome,
        "line": selection.line,
    }


def _selection_from_columns(market_type: str, outcome: str, line: float | None) -> Selection:
    return Selection(market_type=MarketType(market_type), outcome=outcome, line=line)


def odds_quote_to_model(
    odds_quote: OddsQuote, *, bookmaker_id: int, match_id: str | None = None
) -> OddsQuoteModel:
    return OddsQuoteModel(
        match_id=match_id,
        bookmaker_id=bookmaker_id,
        odds_value=odds_quote.odds.value,
        quoted_at=odds_quote.quoted_at,
        **_selection_to_columns(odds_quote.selection),
    )


def odds_quote_from_model(model: OddsQuoteModel) -> OddsQuote:
    return OddsQuote(
        bookmaker=bookmaker_from_model(model.bookmaker),
        selection=_selection_from_columns(model.market_type, model.outcome, model.line),
        odds=DecimalOdds(model.odds_value),
        quoted_at=model.quoted_at,
    )


def team_form_to_model(team_form: TeamForm) -> TeamFormModel:
    return TeamFormModel(
        team_id=team_form.team.id,
        matches_played=team_form.matches_played,
        wins=team_form.wins,
        draws=team_form.draws,
        losses=team_form.losses,
        goals_for=team_form.goals_for,
        goals_against=team_form.goals_against,
    )


def team_form_from_model(model: TeamFormModel) -> TeamForm:
    return TeamForm(
        team=team_from_model(model.team),
        matches_played=model.matches_played,
        wins=model.wins,
        draws=model.draws,
        losses=model.losses,
        goals_for=model.goals_for,
        goals_against=model.goals_against,
    )


def value_bet_to_model(value_bet: ValueBet) -> ValueBetModel:
    return ValueBetModel(
        match_id=value_bet.match.id,
        local_odds=value_bet.local_odds.value,
        fair_probability=value_bet.fair_probability.value,
        edge_percentage=value_bet.edge.value,
        suggested_stake=value_bet.suggested_stake.amount,
        **_selection_to_columns(value_bet.selection),
    )


def value_bet_from_model(model: ValueBetModel) -> ValueBet:
    return ValueBet(
        match=match_from_model(model.match),
        selection=_selection_from_columns(model.market_type, model.outcome, model.line),
        local_odds=DecimalOdds(model.local_odds),
        fair_probability=Probability(model.fair_probability),
        edge=EdgePercentage(model.edge_percentage),
        suggested_stake=Stake(model.suggested_stake),
    )
