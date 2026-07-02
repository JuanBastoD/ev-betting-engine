"""Pure-parsing tests for the three bookmaker Page Objects.

The three .html fixture pairs encode the *same* logical odds content in each
site's own markup, language and decimal format, so every test here runs
parametrized across all scrapers against one shared expected result. The
inline-fragment builders in each SiteSpec generate site-flavored HTML for the
structural error/skip branches.

No Playwright object is involved: `parse_match_odds`/`parse_player_props`
take an HTML string, so the scrapers are constructed with `page=None`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta, timezone

import pytest

from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.player_prop_type import PlayerPropType
from src.infrastructure.providers.scraping.base import AbstractBookmakerScraper
from src.infrastructure.providers.scraping.betano import BetanoScraper
from src.infrastructure.providers.scraping.betplay import BetplayScraper
from src.infrastructure.providers.scraping.exceptions import (
    OddsParsingError,
    ScrapingError,
    SelectorNotFoundError,
)
from src.infrastructure.providers.scraping.stake import StakeScraper


@dataclass(frozen=True)
class SiteSpec:
    scraper_cls: type[AbstractBookmakerScraper]
    match_fixture: str
    props_fixture: str
    match_url: str
    # Builders producing site-flavored HTML fragments for structural edge cases.
    option: Callable[[str, str], str]  # (label, odds) -> one selection row
    option_without_odds: Callable[[str], str]
    wrap_1x2: Callable[[str], str]
    wrap_btts: Callable[[str], str]


BETPLAY = SiteSpec(
    scraper_cls=BetplayScraper,
    match_fixture="betplay_match_odds.html",
    props_fixture="betplay_player_props.html",
    match_url="https://betplay.com.co/apuestas/futbol/junior-fc-vs-america-de-cali",
    option=lambda label, odds: (
        f'<div class="opcion"><span class="opcion-nombre">{label}</span>'
        f'<span class="opcion-cuota">{odds}</span></div>'
    ),
    option_without_odds=lambda label: (
        f'<div class="opcion"><span class="opcion-nombre">{label}</span></div>'
    ),
    wrap_1x2=lambda rows: f'<div class="mercado mercado-ganador">{rows}</div>',
    wrap_btts=lambda rows: f'<div class="mercado mercado-ambos-anotan">{rows}</div>',
)

STAKE = SiteSpec(
    scraper_cls=StakeScraper,
    match_fixture="stake_match_odds.html",
    props_fixture="stake_player_props.html",
    match_url="https://stake.com.co/sports/soccer/junior-fc-vs-america-de-cali",
    option=lambda label, odds: (
        f'<div class="outcome-row"><span class="outcome-name">{label}</span>'
        f'<span class="outcome-odds">{odds}</span></div>'
    ),
    option_without_odds=lambda label: (
        f'<div class="outcome-row"><span class="outcome-name">{label}</span></div>'
    ),
    wrap_1x2=lambda rows: f'<section class="market-group market-winner">{rows}</section>',
    wrap_btts=lambda rows: f'<section class="market-group market-btts">{rows}</section>',
)

BETANO = SiteSpec(
    scraper_cls=BetanoScraper,
    match_fixture="betano_match_odds.html",
    props_fixture="betano_player_props.html",
    match_url="https://betano.com.co/es/futbol/junior-fc-vs-america-de-cali",
    option=lambda label, odds: (
        f'<button data-qa="selection"><span class="selection-title">{label}</span>'
        f'<span class="selection-price">{odds}</span></button>'
    ),
    option_without_odds=lambda label: (
        f'<button data-qa="selection"><span class="selection-title">{label}</span></button>'
    ),
    wrap_1x2=lambda rows: f'<div data-qa="market-1x2">{rows}</div>',
    wrap_btts=lambda rows: f'<div data-qa="market-btts">{rows}</div>',
)

SITES = pytest.mark.parametrize(
    "spec", [BETPLAY, STAKE, BETANO], ids=["betplay", "stake", "betano"]
)

# What every match-odds fixture encodes, regardless of site markup:
# (market_type, outcome, line, odds). The "exactly 2 goals" row present in
# every fixture is a market we don't model and must be skipped.
EXPECTED_MATCH_ODDS = {
    (MarketType.MATCH_WINNER_1X2, "Home", None, 2.10),
    (MarketType.MATCH_WINNER_1X2, "Draw", None, 3.25),
    (MarketType.MATCH_WINNER_1X2, "Away", None, 3.60),
    (MarketType.OVER_UNDER, "Over", 2.5, 1.95),
    (MarketType.OVER_UNDER, "Under", 2.5, 1.80),
    (MarketType.BTTS, "Yes", None, 1.72),
    (MarketType.BTTS, "No", None, 2.05),
}

# What every props fixture encodes: (player, prop_type, outcome, line, odds).
# The goalkeeper-saves row (unsupported prop type) and the "exactly 2" row
# (unrecognized line label) must both be skipped.
EXPECTED_PROPS = {
    ("Carlos Bacca", PlayerPropType.SHOTS_ON_TARGET, "Over", 1.5, 1.85),
    ("Carlos Bacca", PlayerPropType.GOALS, "Over", 0.5, 2.40),
    ("Dorlan Pabón", PlayerPropType.CARDS, "Under", 0.5, 1.45),
    ("Luis Díaz", PlayerPropType.GOALS, "Yes", None, 2.75),
}


def make_scraper(spec: SiteSpec, **kwargs: object) -> AbstractBookmakerScraper:
    return spec.scraper_cls(page=None, **kwargs)


def three_way_1x2(spec: SiteSpec, odds: str = "2,10") -> str:
    return spec.wrap_1x2(
        spec.option("Local", odds) + spec.option("Empate", "3,25") + spec.option("Visitante", "3,60")
    )


@SITES
def test_match_url_is_built_from_the_team_slugs(spec: SiteSpec, match: Match) -> None:
    assert make_scraper(spec).match_url(match) == spec.match_url


@SITES
def test_parse_match_odds_maps_every_supported_market(
    spec: SiteSpec, match: Match, load_fixture: Callable[[str], str]
) -> None:
    quotes = make_scraper(spec).parse_match_odds(load_fixture(spec.match_fixture), match)

    assert {
        (q.selection.market_type, q.selection.outcome, q.selection.line, q.odds.value)
        for q in quotes
    } == EXPECTED_MATCH_ODDS
    assert len(quotes) == len(EXPECTED_MATCH_ODDS)


@SITES
def test_parse_match_odds_marks_quotes_as_local_colombian(
    spec: SiteSpec, match: Match, load_fixture: Callable[[str], str]
) -> None:
    quotes = make_scraper(spec).parse_match_odds(load_fixture(spec.match_fixture), match)

    for quote in quotes:
        assert quote.bookmaker.name == spec.scraper_cls.bookmaker_name
        assert quote.bookmaker.is_sharp is False
        assert quote.bookmaker.region == "CO"
        assert quote.quoted_at.utcoffset() == timedelta(0)


@SITES
def test_region_is_configurable(
    spec: SiteSpec, match: Match, load_fixture: Callable[[str], str]
) -> None:
    quotes = make_scraper(spec, region="LATAM").parse_match_odds(
        load_fixture(spec.match_fixture), match
    )
    assert all(quote.bookmaker.region == "LATAM" for quote in quotes)


@SITES
def test_parse_match_odds_raises_when_the_1x2_block_is_missing(
    spec: SiteSpec, match: Match
) -> None:
    with pytest.raises(SelectorNotFoundError):
        make_scraper(spec).parse_match_odds('<div class="nada"></div>', match)


@SITES
def test_parse_match_odds_raises_when_1x2_does_not_have_three_selections(
    spec: SiteSpec, match: Match
) -> None:
    html = spec.wrap_1x2(spec.option("Local", "2,10") + spec.option("Visitante", "3,60"))
    with pytest.raises(ScrapingError):
        make_scraper(spec).parse_match_odds(html, match)


@SITES
def test_parse_match_odds_with_only_the_1x2_market(spec: SiteSpec, match: Match) -> None:
    quotes = make_scraper(spec).parse_match_odds(three_way_1x2(spec), match)

    assert len(quotes) == 3
    assert {q.selection.outcome for q in quotes} == {"Home", "Draw", "Away"}


@SITES
def test_parse_match_odds_skips_unrecognized_btts_labels(spec: SiteSpec, match: Match) -> None:
    html = three_way_1x2(spec) + spec.wrap_btts(spec.option("Quizás", "1,50"))
    quotes = make_scraper(spec).parse_match_odds(html, match)

    assert len(quotes) == 3  # only the 1X2 quotes; the weird BTTS row is dropped


@SITES
def test_parse_match_odds_raises_when_a_selection_is_missing_its_odds(
    spec: SiteSpec, match: Match
) -> None:
    html = spec.wrap_1x2(
        spec.option("Local", "2,10")
        + spec.option("Empate", "3,25")
        + spec.option_without_odds("Visitante")
    )
    with pytest.raises(SelectorNotFoundError):
        make_scraper(spec).parse_match_odds(html, match)


@SITES
def test_parse_match_odds_raises_on_invalid_odds_text(spec: SiteSpec, match: Match) -> None:
    with pytest.raises(OddsParsingError):
        make_scraper(spec).parse_match_odds(three_way_1x2(spec, odds="N/A"), match)


@SITES
def test_parse_player_props_maps_supported_props_and_skips_the_rest(
    spec: SiteSpec, match: Match, load_fixture: Callable[[str], str]
) -> None:
    props = make_scraper(spec).parse_player_props(load_fixture(spec.props_fixture), match)

    assert {
        (p.player_name, p.prop_type, p.outcome, p.line, p.odds.value) for p in props
    } == EXPECTED_PROPS
    assert len(props) == len(EXPECTED_PROPS)


@SITES
def test_parse_player_props_builds_self_contained_domain_objects(
    spec: SiteSpec, match: Match, load_fixture: Callable[[str], str]
) -> None:
    props = make_scraper(spec).parse_player_props(load_fixture(spec.props_fixture), match)

    for prop in props:
        assert prop.match is match
        assert prop.bookmaker.name == spec.scraper_cls.bookmaker_name
        assert prop.bookmaker.is_sharp is False
        assert prop.bookmaker.region == "CO"
        assert prop.quoted_at.tzinfo is timezone.utc


@SITES
def test_parse_player_props_returns_empty_for_a_page_without_props(
    spec: SiteSpec, match: Match
) -> None:
    assert make_scraper(spec).parse_player_props('<div class="vacio"></div>', match) == []
