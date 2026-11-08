"""The page's static structure: code panes scroll instead of spilling out (lrusso3, round 5)."""

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
