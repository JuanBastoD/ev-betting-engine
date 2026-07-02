"""Tiny stdlib-only HTML fragment parser used by the bookmaker scrapers.

Playwright is used strictly for navigation and for grabbing `inner_html` of
the relevant containers; everything after that runs through this module, so
the per-bookmaker parsing logic is pure (HTML string in, domain objects out)
and testable against local .html fixtures without ever launching a browser.

Deliberately minimal: class- and attribute-based lookup over a lenient tree,
which is all the scrapers need. If selector needs ever outgrow this, adding a
real parser dependency (e.g. selectolax) is the moment to revisit.
"""

from dataclasses import dataclass, field
from html.parser import HTMLParser

# HTML void elements: they never take a closing tag, so they must not be
# pushed onto the open-element stack or they would swallow their siblings.
_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
)


@dataclass(slots=True)
class Element:
    """One parsed element. `content` interleaves text chunks and child
    elements in document order so `text` reads naturally."""

    tag: str
    attrs: dict[str, str]
    content: list["Element | str"] = field(default_factory=list)

    @property
    def classes(self) -> frozenset[str]:
        return frozenset(self.attrs.get("class", "").split())

    @property
    def text(self) -> str:
        """All descendant text in document order, whitespace-normalized."""
        parts: list[str] = []
        self._collect_text(parts)
        return " ".join(" ".join(parts).split())

    def _collect_text(self, parts: list[str]) -> None:
        for item in self.content:
            if isinstance(item, str):
                parts.append(item)
            else:
                item._collect_text(parts)

    def _child_elements(self) -> list["Element"]:
        return [item for item in self.content if isinstance(item, Element)]

    def find_all(self, class_name: str) -> list["Element"]:
        """Descendants carrying `class_name`, in document order (self excluded)."""
        found: list[Element] = []
        for child in self._child_elements():
            if class_name in child.classes:
                found.append(child)
            found.extend(child.find_all(class_name))
        return found

    def find(self, class_name: str) -> "Element | None":
        matches = self.find_all(class_name)
        return matches[0] if matches else None

    def find_all_by_attr(self, name: str, value: str) -> list["Element"]:
        """Descendants whose attribute `name` equals `value`, in document order."""
        found: list[Element] = []
        for child in self._child_elements():
            if child.attrs.get(name) == value:
                found.append(child)
            found.extend(child.find_all_by_attr(name, value))
        return found

    def find_by_attr(self, name: str, value: str) -> "Element | None":
        matches = self.find_all_by_attr(name, value)
        return matches[0] if matches else None


class _FragmentParser(HTMLParser):
    """Lenient parser: unmatched closing tags are ignored, unclosed tags are
    implicitly closed at the end - scraped markup is rarely pristine."""

    def __init__(self) -> None:
        super().__init__()
        self.root = Element(tag="#fragment", attrs={})
        self._stack: list[Element] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag=tag, attrs={name: value or "" for name, value in attrs})
        self._stack[-1].content.append(element)
        if tag not in _VOID_TAGS:
            self._stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag=tag, attrs={name: value or "" for name, value in attrs})
        self._stack[-1].content.append(element)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return
        # Closing tag with no matching open element: ignore it.

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._stack[-1].content.append(data)


def parse_html_fragment(html: str) -> Element:
    """Parse an HTML fragment (as returned by Playwright's `inner_html`) into
    a synthetic root Element."""
    parser = _FragmentParser()
    parser.feed(html)
    parser.close()
    return parser.root
