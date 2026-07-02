"""Page Object for Betplay (betplay.com.co) match pages.

Betplay renders Spanish labels with comma decimals ('Más de 2,5' @ '1,85').
Every selector and label convention for the site lives in this class only.
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
class BetplayScraper(AbstractBookmakerScraper):
    bookmaker_name: ClassVar[str] = "Betplay"
    default_base_url: ClassVar[str] = "https://betplay.com.co"
    match_page_ready_selector: ClassVar[str] = ".evento-detalle"
    match_odds_container_selector: ClassVar[str] = ".evento-detalle .mercados-principales"
    props_tab_selector: ClassVar[str] = "[data-tab='jugadores']"
    props_container_selector: ClassVar[str] = ".mercados-jugadores"

    _OVER_PREFIX: ClassVar[str] = "más de"
    _UNDER_PREFIX: ClassVar[str] = "menos de"
    _BTTS_OUTCOMES: ClassVar[dict[str, str]] = {"sí": "Yes", "no": "No"}
    _PROP_TYPES: ClassVar[dict[str, PlayerPropType]] = {
        "goles": PlayerPropType.GOALS,
        "tiros a puerta": PlayerPropType.SHOTS_ON_TARGET,
        "asistencias": PlayerPropType.ASSISTS,
        "tarjetas": PlayerPropType.CARDS,
        "anota en cualquier momento": PlayerPropType.GOALS,
    }

    def match_url(self, match: Match) -> str:
        return (
            f"{self._base_url}/apuestas/futbol/"
            f"{slugify(match.home_team.name)}-vs-{slugify(match.away_team.name)}"
        )

    def parse_match_odds(self, html: str, match: Match) -> list[OddsQuote]:
        root = parse_html_fragment(html)
        quoted_at = datetime.now(timezone.utc)
        quotes: list[OddsQuote] = []

        winner = root.find("mercado-ganador")
        if winner is None:
            raise SelectorNotFoundError("Betplay: 1X2 block ('mercado-ganador') not found")
        options = winner.find_all("opcion")
        if len(options) != 3:
            raise ScrapingError(
                f"Betplay: expected 3 selections in the 1X2 market, found {len(options)}"
            )
        for outcome, option in zip(_1X2_OUTCOMES, options):
            quotes.append(
                self._quote(
                    match=match,
                    market_type=MarketType.MATCH_WINNER_1X2,
                    outcome=outcome,
                    odds_text=self._required_text(option, "opcion-cuota"),
                    quoted_at=quoted_at,
                )
            )

        totals = root.find("mercado-totales")
        if totals is not None:
            for option in totals.find_all("opcion"):
                label = self._required_text(option, "opcion-nombre")
                parsed = self._parse_over_under_label(
                    label, over_prefix=self._OVER_PREFIX, under_prefix=self._UNDER_PREFIX
                )
                if parsed is None:
                    continue
                outcome, line = parsed
                quotes.append(
                    self._quote(
                        match=match,
                        market_type=MarketType.OVER_UNDER,
                        outcome=outcome,
                        line=line,
                        odds_text=self._required_text(option, "opcion-cuota"),
                        quoted_at=quoted_at,
                    )
                )

        btts = root.find("mercado-ambos-anotan")
        if btts is not None:
            for option in btts.find_all("opcion"):
                label = self._required_text(option, "opcion-nombre").casefold()
                outcome_name = self._BTTS_OUTCOMES.get(label)
                if outcome_name is None:
                    continue
                quotes.append(
                    self._quote(
                        match=match,
                        market_type=MarketType.BTTS,
                        outcome=outcome_name,
                        odds_text=self._required_text(option, "opcion-cuota"),
                        quoted_at=quoted_at,
                    )
                )

        return quotes

    def parse_player_props(self, html: str, match: Match) -> list[PlayerPropMarket]:
        root = parse_html_fragment(html)
        quoted_at = datetime.now(timezone.utc)
        props: list[PlayerPropMarket] = []

        for card in root.find_all("prop-jugador"):
            market_label = self._required_text(card, "prop-mercado").casefold()
            prop_type = self._PROP_TYPES.get(market_label)
            if prop_type is None:
                continue

            line_element = card.find("prop-linea")
            if line_element is None:
                # Lineless prop (e.g. anytime goalscorer): the bet is a plain yes.
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
                    player_name=self._required_text(card, "prop-nombre"),
                    prop_type=prop_type,
                    outcome=outcome,
                    line=line,
                    odds_text=self._required_text(card, "prop-cuota"),
                    quoted_at=quoted_at,
                )
            )

        return props
