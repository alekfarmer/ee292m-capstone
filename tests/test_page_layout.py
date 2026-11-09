"""The page's static structure: code panes scroll instead of spilling out (lrusso3, round 5)."""

import re
from html.parser import HTMLParser

from app.paths import WEB_DIR


class _CodeParents(HTMLParser):
    """Record, for each element with class ``code``, the classes of its ancestors."""

    def __init__(self) -> None:
        super().__init__()
        self._stack: list[tuple[str, set[str]]] = []
        self.code_elements: list[tuple[str, list[set[str]]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = set((dict(attrs).get("class") or "").split())
        ident = dict(attrs).get("id") or tag
        if "code" in classes:
            self.code_elements.append((ident, [c for _, c in self._stack]))
        if tag not in {"br", "img", "input", "meta", "link", "hr", "source", "wbr"}:
            self._stack.append((tag, classes))

    def handle_endtag(self, tag: str) -> None:
        while self._stack:
            open_tag, _ = self._stack.pop()
            if open_tag == tag:
                break


def test_every_code_pane_sits_in_a_scroll_container() -> None:
    """A long C or asm line scrolls inside its pane instead of running past its edge."""
    parser = _CodeParents()
    parser.feed((WEB_DIR / "index.html").read_text())
    assert parser.code_elements, "no element with class 'code' on the page"
    spilling = [
        ident
        for ident, ancestors in parser.code_elements
        if not any("code-scroll" in classes for classes in ancestors)
    ]
    assert not spilling, f"code shown outside a .code-scroll container: {spilling}"


def _css_rule(selector: str) -> str:
    """The body of the stylesheet rule whose selector is exactly ``selector``."""
    css = (WEB_DIR / "styles.css").read_text()
    match = re.search(r"(?:^|\}|\*/)\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match, f"no rule for {selector!r} in styles.css"
    return match.group(1)


def test_playing_never_scrolls_the_window() -> None:
    """Following the current instruction scrolls the asm pane only, not the page (user, round 6).

    ``scrollIntoView`` scrolls every enclosing box, the window included, so a
    reader who scrolled down to the datapath was pulled back up each cycle.
    """
    assert ".scrollIntoView(" not in (WEB_DIR / "app.js").read_text()


def test_a_tall_view_can_be_fitted_to_the_height() -> None:
    """A tall, narrow block (the result mux) fits on screen (user, round 6)."""
    assert 'id="fit-height"' in (WEB_DIR / "index.html").read_text()
    assert "height" in _css_rule(".view.fit-height svg")


def test_the_explanation_keeps_one_height() -> None:
    """The panel does not grow and shrink with each cycle's text (user, round 6)."""
    rule = _css_rule(".explain-body")
    assert re.search(r"(?:^|;)\s*height\s*:", rule), f"no fixed height in .explain-body: {rule}"


def test_changed_wires_are_highlighted_gold() -> None:
    """The legend's gold bar matches the drawing: a wide gold halo, not just bold (round 6)."""
    rule = _css_rule("svg.netview .wire-halo")
    assert "var(--changed)" in rule
    width = re.search(r"stroke-width\s*:\s*([\d.]+)", rule)
    assert width and float(width.group(1)) >= 3, rule
    assert "wire-halo" in (WEB_DIR / "graph.js").read_text()
