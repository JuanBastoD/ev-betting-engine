from src.infrastructure.providers.scraping.html_utils import parse_html_fragment


def test_find_all_returns_descendants_in_document_order() -> None:
    root = parse_html_fragment(
        '<div class="row"><span class="odds">1,50</span></div>'
        '<div class="row"><span class="odds">2,75</span></div>'
    )
    assert [element.text for element in root.find_all("odds")] == ["1,50", "2,75"]


def test_find_matches_one_class_among_many() -> None:
    root = parse_html_fragment('<div class="mercado mercado-ganador destacado"></div>')
    found = root.find("mercado-ganador")
    assert found is not None
    assert found.tag == "div"
    assert found.classes == {"mercado", "mercado-ganador", "destacado"}


def test_find_returns_none_when_class_is_absent() -> None:
    root = parse_html_fragment('<div class="otra"></div>')
    assert root.find("mercado-ganador") is None


def test_find_all_searches_nested_elements() -> None:
    root = parse_html_fragment(
        '<section><div class="grupo"><div class="opcion">a</div></div>'
        '<div class="opcion">b</div></section>'
    )
    assert [element.text for element in root.find_all("opcion")] == ["a", "b"]


def test_text_concatenates_descendants_in_document_order() -> None:
    root = parse_html_fragment("<span>Más de <b>2,5</b> goles</span>")
    assert root.text == "Más de 2,5 goles"


def test_text_normalizes_whitespace() -> None:
    root = parse_html_fragment("<span>\n   Junior   FC \t </span>")
    assert root.text == "Junior FC"


def test_void_elements_do_not_swallow_their_siblings() -> None:
    root = parse_html_fragment('<div><br><span class="odds">1,50</span></div>')
    found = root.find("odds")
    assert found is not None
    assert found.text == "1,50"


def test_self_closing_tags_are_handled() -> None:
    root = parse_html_fragment('<div><img src="logo.png"/><span class="odds">2,10</span></div>')
    found = root.find("odds")
    assert found is not None
    assert found.text == "2,10"


def test_unmatched_closing_tags_are_ignored() -> None:
    root = parse_html_fragment('</p><div class="row">ok</div></section>')
    found = root.find("row")
    assert found is not None
    assert found.text == "ok"


def test_closing_an_outer_tag_implicitly_closes_unclosed_inner_tags() -> None:
    root = parse_html_fragment('<div class="outer"><span class="inner">a</div><b class="after">b</b>')
    outer = root.find("outer")
    after = root.find("after")
    assert outer is not None
    assert outer.text == "a"
    assert after is not None
    assert outer.find("after") is None  # 'after' is a sibling, not swallowed by 'outer'


def test_unclosed_tags_are_implicitly_closed_at_the_end() -> None:
    root = parse_html_fragment('<div class="a"><span class="b">texto')
    found = root.find("b")
    assert found is not None
    assert found.text == "texto"


def test_valueless_attributes_become_empty_strings() -> None:
    root = parse_html_fragment('<button class="cuota" disabled>1,95</button>')
    found = root.find("cuota")
    assert found is not None
    assert found.attrs["disabled"] == ""


def test_find_by_attr_matches_attribute_values() -> None:
    root = parse_html_fragment(
        '<div data-qa="market-1x2"><button data-qa="selection">a</button>'
        '<button data-qa="selection">b</button></div>'
    )
    market = root.find_by_attr("data-qa", "market-1x2")
    assert market is not None
    assert [element.text for element in market.find_all_by_attr("data-qa", "selection")] == ["a", "b"]


def test_find_by_attr_returns_none_when_absent() -> None:
    root = parse_html_fragment('<div data-qa="otro"></div>')
    assert root.find_by_attr("data-qa", "market-1x2") is None


def test_elements_without_class_have_no_classes() -> None:
    root = parse_html_fragment("<div><span>text</span></div>")
    assert root.find("anything") is None
