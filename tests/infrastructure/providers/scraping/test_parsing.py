import pytest

from src.infrastructure.providers.scraping.exceptions import OddsParsingError
from src.infrastructure.providers.scraping.parsing import (
    parse_decimal_odds,
    parse_line_value,
    slugify,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2,35", 2.35),
        ("1.87", 1.87),
        ("  3,10  ", 3.10),
        ("2", 2.0),
        ("10,00", 10.0),
    ],
)
def test_parse_decimal_odds_accepts_local_number_formats(text: str, expected: float) -> None:
    assert parse_decimal_odds(text).value == expected


@pytest.mark.parametrize("text", ["", "   ", "N/A", "abc", "2,3,5", "1x2", "-2,10", "2,10 EUR"])
def test_parse_decimal_odds_rejects_non_numeric_text(text: str) -> None:
    with pytest.raises(OddsParsingError):
        parse_decimal_odds(text)


@pytest.mark.parametrize("text", ["1,00", "0,95", "1"])
def test_parse_decimal_odds_rejects_values_violating_the_domain_invariant(text: str) -> None:
    with pytest.raises(OddsParsingError):
        parse_decimal_odds(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Más de 2,5", 2.5),
        ("Menos de 3,5", 3.5),
        ("Over 1.5", 1.5),
        ("2.5", 2.5),
    ],
)
def test_parse_line_value_extracts_the_threshold(text: str, expected: float) -> None:
    assert parse_line_value(text) == expected


def test_parse_line_value_rejects_text_without_a_number() -> None:
    with pytest.raises(OddsParsingError):
        parse_line_value("Más de goles")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Junior FC", "junior-fc"),
        ("  America de Cali  ", "america-de-cali"),
        ("Atlético Nacional", "atl-tico-nacional"),
        ("---", "unknown"),
    ],
)
def test_slugify_derives_url_slugs_from_team_names(name: str, expected: str) -> None:
    assert slugify(name) == expected
