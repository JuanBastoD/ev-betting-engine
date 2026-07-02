"""Page Object for Stake (stake.com.co) match pages.

Stake renders English labels with dot decimals ('Over 2.5' @ '1.87').
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
class StakeScraper(AbstractBookmakerScraper):
    bookmaker_name: ClassVar[str] = "Stake"
    default_base_url: ClassVar[str] = "https://stake.com.co"
    match_page_ready_selector: ClassVar[str] = ".event-detail"
    match_odds_container_selector: ClassVar[str] = ".event-detail .main-markets"
    props_tab_selector: ClassVar[str] = "[data-tab='player-props']"
    props_container_selector: ClassVar[str] = ".player-props"

    _OVER_PREFIX: ClassVar[str] = "over"
    _UNDER_PREFIX: ClassVar[str] = "under"
    _BTTS_OUTCOMES: ClassVar[dict[str, str]] = {"yes": "Yes", "no": "No"}
    _PROP_TYPES: ClassVar[dict[str, PlayerPropType]] = {
        "goals": PlayerPropType.GOALS,
        "shots on target": PlayerPropType.SHOTS_ON_TARGET,
        "assists": PlayerPropType.ASSISTS,
        "cards": PlayerPropType.CARDS,
        "anytime goalscorer": PlayerPropType.GOALS,
    }

    def match_url(self, match: Match) -> str:
        return (
            f"{self._base_url}/sports/soccer/"
            f"{slugify(match.home_team.name)}-vs-{slugify(match.away_team.name)}"
        )

    def parse_match_odds(self, html: str, match: Match) -> list[OddsQuote]:
        root = parse_html_fragment(html)
        quoted_at = datetime.now(timezone.utc)
        quotes: list[OddsQuote] = []

        winner = root.find("market-winner")
        if winner is None:
            raise SelectorNotFoundError("Stake: 1X2 block ('market-winner') not found")
        rows = winner.find_all("outcome-row")
        if len(rows) != 3:
            raise ScrapingError(
                f"Stake: expected 3 selections in the 1X2 market, found {len(rows)}"
            )
        for outcome, row in zip(_1X2_OUTCOMES, rows):
            quotes.append(
                self._quote(
                    market_type=MarketType.MATCH_WINNER_1X2,
                    outcome=outcome,
                    odds_text=self._required_text(row, "outcome-odds"),
                    quoted_at=quoted_at,
                )
            )

        totals = root.find("market-totals")
        if totals is not None:
            for row in totals.find_all("outcome-row"):
                label = self._required_text(row, "outcome-name")
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
                        odds_text=self._required_text(row, "outcome-odds"),
                        quoted_at=quoted_at,
                    )
                )

        btts = root.find("market-btts")
        if btts is not None:
            for row in btts.find_all("outcome-row"):
                label = self._required_text(row, "outcome-name").casefold()
                outcome_name = self._BTTS_OUTCOMES.get(label)
                if outcome_name is None:
                    continue
                quotes.append(
                    self._quote(
                        market_type=MarketType.BTTS,
                        outcome=outcome_name,
                        odds_text=self._required_text(row, "outcome-odds"),
                        quoted_at=quoted_at,
                    )
                )

        return quotes

    def parse_player_props(self, html: str, match: Match) -> list[PlayerPropMarket]:
        root = parse_html_fragment(html)
        quoted_at = datetime.now(timezone.utc)
        props: list[PlayerPropMarket] = []

        for row in root.find_all("prop-row"):
            market_label = self._required_text(row, "prop-market").casefold()
            prop_type = self._PROP_TYPES.get(market_label)
            if prop_type is None:
                continue

            line_element = row.find("prop-line")
            if line_element is None:
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
                    player_name=self._required_text(row, "prop-player"),
                    prop_type=prop_type,
                    outcome=outcome,
                    line=line,
                    odds_text=self._required_text(row, "prop-odds"),
                    quoted_at=quoted_at,
                )
            )

        return props
