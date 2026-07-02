"""Page Object for Betano (betano.com.co) match pages.

Betano marks its widgets with `data-qa` attributes rather than semantic
classes, and renders Spanish labels with comma decimals. Every selector and
label convention for the site lives in this class only.
"""

from datetime import datetime, timezone
from typing import ClassVar

from src.domain.entities.market_type import MarketType
from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.entities.player_prop_market import PlayerPropMarket
from src.domain.entities.player_prop_type import PlayerPropType
from src.infrastructure.providers.scraping.base import AbstractBookmakerScraper
from src.infrastructure.providers.scraping.exceptions import ScrapingError, SelectorNotFoundError
from src.infrastructure.providers.scraping.factory import ScraperFactory
from src.infrastructure.providers.scraping.html_utils import parse_html_fragment
from src.infrastructure.providers.scraping.parsing import slugify

_1X2_OUTCOMES = ("Home", "Draw", "Away")


@ScraperFactory.register
class BetanoScraper(AbstractBookmakerScraper):
    bookmaker_name: ClassVar[str] = "Betano"
    default_base_url: ClassVar[str] = "https://betano.com.co"
    match_page_ready_selector: ClassVar[str] = "[data-qa='event-detail']"
    match_odds_container_selector: ClassVar[str] = "[data-qa='event-markets']"
    props_tab_selector: ClassVar[str] = "[data-qa='tab-jugadores']"
    props_container_selector: ClassVar[str] = "[data-qa='player-markets']"

    _OVER_PREFIX: ClassVar[str] = "más de"
    _UNDER_PREFIX: ClassVar[str] = "menos de"
    _BTTS_OUTCOMES: ClassVar[dict[str, str]] = {"sí": "Yes", "no": "No"}
    _PROP_TYPES: ClassVar[dict[str, PlayerPropType]] = {
        "goles": PlayerPropType.GOALS,
        "tiros a puerta": PlayerPropType.SHOTS_ON_TARGET,
        "asistencias": PlayerPropType.ASSISTS,
        "tarjetas": PlayerPropType.CARDS,
        "jugador anota": PlayerPropType.GOALS,
    }

    def match_url(self, match: Match) -> str:
        return (
            f"{self._base_url}/es/futbol/"
            f"{slugify(match.home_team.name)}-vs-{slugify(match.away_team.name)}"
        )

    def parse_match_odds(self, html: str, match: Match) -> list[OddsQuote]:
        root = parse_html_fragment(html)
        quoted_at = datetime.now(timezone.utc)
        quotes: list[OddsQuote] = []

        winner = root.find_by_attr("data-qa", "market-1x2")
        if winner is None:
            raise SelectorNotFoundError("Betano: 1X2 block ([data-qa='market-1x2']) not found")
        selections = winner.find_all_by_attr("data-qa", "selection")
        if len(selections) != 3:
            raise ScrapingError(
                f"Betano: expected 3 selections in the 1X2 market, found {len(selections)}"
            )
        for outcome, selection in zip(_1X2_OUTCOMES, selections):
            quotes.append(
                self._quote(
                    market_type=MarketType.MATCH_WINNER_1X2,
                    outcome=outcome,
                    odds_text=self._required_text(selection, "selection-price"),
                    quoted_at=quoted_at,
                )
            )

        totals = root.find_by_attr("data-qa", "market-totales")
        if totals is not None:
            for selection in totals.find_all_by_attr("data-qa", "selection"):
                label = self._required_text(selection, "selection-title")
                parsed = self._parse_over_under_label(
                    label, over_prefix=self._OVER_PREFIX, under_prefix=self._UNDER_PREFIX
                )
                if parsed is None:
                    continue
                outcome, line = parsed
                quotes.append(
                    self._quote(
                        market_type=MarketType.OVER_UNDER,
                        outcome=outcome,
                        line=line,
                        odds_text=self._required_text(selection, "selection-price"),
                        quoted_at=quoted_at,
                    )
                )

        btts = root.find_by_attr("data-qa", "market-btts")
        if btts is not None:
            for selection in btts.find_all_by_attr("data-qa", "selection"):
                label = self._required_text(selection, "selection-title").casefold()
                outcome_name = self._BTTS_OUTCOMES.get(label)
                if outcome_name is None:
                    continue
                quotes.append(
                    self._quote(
                        market_type=MarketType.BTTS,
                        outcome=outcome_name,
                        odds_text=self._required_text(selection, "selection-price"),
                        quoted_at=quoted_at,
                    )
                )

        return quotes

    def parse_player_props(self, html: str, match: Match) -> list[PlayerPropMarket]:
        root = parse_html_fragment(html)
        quoted_at = datetime.now(timezone.utc)
        props: list[PlayerPropMarket] = []

        for card in root.find_all_by_attr("data-qa", "player-prop"):
            market_label = self._required_text(card, "prop-title").casefold()
            prop_type = self._PROP_TYPES.get(market_label)
            if prop_type is None:
                continue

            line_element = card.find("prop-line")
            if line_element is None:
                # Lineless prop (e.g. 'Jugador anota'): the bet is a plain yes.
                outcome, line = "Yes", None
            else:
                parsed = self._parse_over_under_label(
                    line_element.text,
                    over_prefix=self._OVER_PREFIX,
                    under_prefix=self._UNDER_PREFIX,
                )
                if parsed is None:
                    continue
                outcome, line = parsed

            props.append(
                self._prop(
                    match=match,
                    player_name=self._required_text(card, "prop-player"),
                    prop_type=prop_type,
                    outcome=outcome,
                    line=line,
                    odds_text=self._required_text(card, "prop-price"),
                    quoted_at=quoted_at,
                )
            )

        return props
