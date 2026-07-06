from datetime import datetime, timezone

from src.application.use_cases.ingest_local_odds import IngestLocalOddsUseCase
from src.domain.entities.bookmaker import Bookmaker
from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.entities.player_prop_type import PlayerPropType
from src.domain.entities.selection import Selection
from src.domain.value_objects.decimal_odds import DecimalOdds
from tests.fakes import FakeLocalOddsProvider, FakeOddsRepository

LOCAL_BOOKMAKER = Bookmaker(name="Betplay", is_sharp=False, region="CO")


def _quote(match: Match, outcome: str, odds_value: float) -> OddsQuote:
    return OddsQuote(
        match=match,
        bookmaker=LOCAL_BOOKMAKER,
        selection=Selection(market_type=MarketType.MATCH_WINNER_1X2, outcome=outcome),
        odds=DecimalOdds(odds_value),
        quoted_at=datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc),
    )


def _prop(match: Match) -> PlayerPropMarket:
    return PlayerPropMarket(
        match=match,
        bookmaker=LOCAL_BOOKMAKER,
        player_name="Carlos Bacca",
        prop_type=PlayerPropType.SHOTS_ON_TARGET,
        outcome="Over",
        line=1.5,
        odds=DecimalOdds(1.90),
        quoted_at=datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc),
    )


async def test_execute_persists_main_market_odds_and_returns_props_unpersisted(
    match: Match,
) -> None:
    quotes = [_quote(match, "Home", 2.30)]
    props = [_prop(match)]
    local_odds_provider = FakeLocalOddsProvider(
        quotes_by_match_id={match.id: quotes}, props_by_match_id={match.id: props}
    )
    odds_repository = FakeOddsRepository()

    use_case = IngestLocalOddsUseCase(
        local_odds_provider=local_odds_provider, odds_repository=odds_repository
    )
    result = await use_case.execute(match)

    assert result.local_quotes == quotes
    assert result.prop_markets == props
    assert odds_repository.saved == quotes  # only main-market quotes are persisted


async def test_execute_with_no_props_offered_returns_an_empty_list(match: Match) -> None:
    local_odds_provider = FakeLocalOddsProvider(quotes_by_match_id={match.id: [_quote(match, "Home", 2.30)]})
    odds_repository = FakeOddsRepository()

    use_case = IngestLocalOddsUseCase(
        local_odds_provider=local_odds_provider, odds_repository=odds_repository
    )
    result = await use_case.execute(match)

    assert result.prop_markets == []
