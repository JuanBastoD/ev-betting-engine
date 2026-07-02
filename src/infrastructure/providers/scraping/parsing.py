"""Pure text-parsing helpers shared by every bookmaker scraper.

Local sites render numbers with Spanish formatting (comma as decimal
separator), so all numeric parsing is comma/dot tolerant. Everything here is
side-effect free - the whole module is testable without a browser.
"""

import re

from src.domain.value_objects.decimal_odds import DecimalOdds
from src.infrastructure.providers.scraping.exceptions import OddsParsingError

_ODDS_PATTERN = re.compile(r"^\d+(?:[.,]\d+)?$")
_LINE_PATTERN = re.compile(r"\d+(?:[.,]\d+)?")
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def parse_decimal_odds(text: str) -> DecimalOdds:
    """Convert scraped odds text (e.g. '2,35', ' 1.87 ') into DecimalOdds.

    Raises OddsParsingError for non-numeric text and for numeric values that
    violate the DecimalOdds invariant (<= 1.0), so callers deal with a single
    failure mode at this boundary.
    """
    cleaned = text.strip()
    if not _ODDS_PATTERN.match(cleaned):
        raise OddsParsingError(f"Scraped odds text is not a decimal number: {text!r}")
    value = float(cleaned.replace(",", "."))
    try:
        return DecimalOdds(value)
    except ValueError as exc:
        raise OddsParsingError(f"Scraped odds text is not valid decimal odds: {text!r}") from exc


def parse_line_value(text: str) -> float:
    """Extract the numeric threshold from a line label such as
    'Más de 2,5', 'Over 1.5' or 'Menos de 3,5'."""
    found = _LINE_PATTERN.search(text)
    if found is None:
        raise OddsParsingError(f"No numeric line found in scraped text: {text!r}")
    return float(found.group(0).replace(",", "."))


def slugify(name: str) -> str:
    """Derive a URL slug from a team name, for building match-page URLs."""
    slug = _SLUG_PATTERN.sub("-", name.strip().lower()).strip("-")
    return slug or "unknown"
