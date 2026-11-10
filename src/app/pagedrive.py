"""Drive the real page in headless Chromium and measure it, for ``make smoke``.

``pagecheck`` reads the page's DOM once its scripts have run; it cannot
measure a box, scroll the window or press a button. This module starts the
same Chromium with its DevTools port open on 127.0.0.1, then uses the DevTools
protocol to load a page, run JavaScript in it and read the answers: box sizes,
computed styles, the window's scroll position. Each ``check_*`` function
returns a list of problems (empty if the page behaves).

The checks replace tests that searched the page's source files for text
(round 6): those passed when the text was there, not when the page behaved.
"""

import json
import tempfile
import time
import urllib.request
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from websockets.sync.client import ClientConnection, connect

from app.errors import ToolError
from app.pagecheck import BASE, CHROMIUM
from app.tools import ToolStream

WIDTH, HEIGHT = 1600, 1000  # the window, in CSS pixels
WAIT_S = 20.0  # longest wait for the page to load, draw or build
LIFETIME_S = 300.0  # the watchdog's limit on one Chromium session


class Browser:
    """One headless Chromium with a single page, driven over DevTools.

    Use as a context manager; leaving it stops Chromium.
    """

    def __init__(self, base: str = BASE) -> None:
        """Start Chromium and connect to its page, which will show the app at ``base``.

        Raises:
            ToolError: Chromium is missing, or its DevTools port never opened.
        """
        self._profile = tempfile.TemporaryDirectory(prefix="chromium-")
        profile = Path(self._profile.name)
        self._chromium = ToolStream(
            [
                CHROMIUM,
                "--no-sandbox",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--window-size={WIDTH},{HEIGHT}",
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=0",  # any free port, written to the profile
                f"--user-data-dir={profile}",
                "about:blank",
            ],
            timeout=LIFETIME_S,
            log=profile.parent / f"{profile.name}.log",
        )
        self._base = base
        self._next_id = 0
        try:
            port = self._devtools_port(profile / "DevToolsActivePort")
            self._ws: ClientConnection = connect(self._page_socket(port), max_size=None)
        except BaseException:
            self.close()
            raise

    def _devtools_port(self, active_port: Path) -> int:
        deadline = time.monotonic() + WAIT_S
        while time.monotonic() < deadline:
            if not self._chromium.running():
                raise ToolError(f"{CHROMIUM} exited before opening its DevTools port")
            lines = active_port.read_text().splitlines() if active_port.exists() else []
            if lines and lines[0].isdigit():
                return int(lines[0])
            time.sleep(0.05)
        raise ToolError(f"{CHROMIUM} did not open its DevTools port within {WAIT_S:g} s")

    @staticmethod
    def _page_socket(port: int) -> str:
        url = f"http://127.0.0.1:{port}/json/list"
        with urllib.request.urlopen(url, timeout=10) as resp:
            targets = json.load(resp)
        pages = [t["webSocketDebuggerUrl"] for t in targets if t.get("type") == "page"]
        if not pages:
            raise ToolError(f"{CHROMIUM} has no page to drive")
        return str(pages[0])

    def __enter__(self) -> Self:
        """Return the browser."""
        return self

    def __exit__(
        self,
        _type: type[BaseException] | None,
        _value: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        """Stop Chromium."""
        self.close()

    def close(self) -> None:
        """Disconnect, stop Chromium and remove its profile."""
        ws = getattr(self, "_ws", None)
        if ws is not None:
            ws.close()
        self._chromium.__exit__(None, None, None)
        self._profile.cleanup()

    def _send(self, method: str, **params: object) -> dict[str, Any]:
        """Call one DevTools method and return its result (events are skipped)."""
        self._next_id += 1
        ident = self._next_id
        self._ws.send(json.dumps({"id": ident, "method": method, "params": params}))
        while True:
            message = json.loads(self._ws.recv(timeout=WAIT_S))
            if message.get("id") != ident:
                continue
            if "error" in message:
                raise ToolError(f"DevTools {method}: {message['error'].get('message')}")
            result: dict[str, Any] = message.get("result", {})
            return result

    def js(self, expression: str) -> Any:  # noqa: ANN401 - whatever JSON the page answers
        """Evaluate ``expression`` in the page (promises are awaited) and return its value.

        Raises:
            ToolError: the expression threw.
        """
        result = self._send(
            "Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True
        )
        if "exceptionDetails" in result:
            detail = result["exceptionDetails"]
            text = detail.get("exception", {}).get("description") or detail.get("text")
            raise ToolError(f"the page threw: {text}")
        return result.get("result", {}).get("value")

    def wait_for(self, expression: str, what: str, timeout: float = WAIT_S) -> Any:  # noqa: ANN401
        """Poll ``expression`` until it is truthy, and return its value.

        Raises:
            ToolError: it stayed falsy for ``timeout`` seconds (``what`` says what was awaited).
        """
        deadline = time.monotonic() + timeout
        while True:
            value = self.js(expression)
            if value:
                return value
            if time.monotonic() > deadline:
                raise ToolError(f"waited {timeout:g} s for {what}")
            time.sleep(0.05)

    def open(self, fragment: str) -> None:
        """Load the page at ``fragment`` (always a fresh load) and wait until it is drawn."""
        self._send("Page.navigate", url="about:blank")
        self._send("Page.navigate", url=self._base + fragment)
        self.wait_for("document.getElementById('view')?.dataset.drawn", f"the page at {fragment}")

    def drawn(self) -> str:
        """What the page says it has drawn: ``program:cycle:view``."""
        return str(self.js("document.getElementById('view').dataset.drawn"))

    def step_to(self, cycle: int) -> None:
        """Press "cycle ▶" until the page has drawn ``cycle`` (only forward)."""
        while int(self.drawn().split(":")[1]) < cycle:
            before = self.drawn()
            self.js("document.getElementById('next').click()")
            self.wait_for(
                f"document.getElementById('view').dataset.drawn !== {json.dumps(before)}",
                "the next cycle to be drawn",
            )


def check_code_panes_scroll(page: Browser) -> list[str]:
    """A long C line scrolls inside the C pane instead of running past its box (round 5)."""
    page.open("#program=tour&cycle=0")
    box = page.js(
        """(() => {
          const pane = document.getElementById('c-view');
          const panel = pane.closest('section') ?? pane.parentElement;
          return {wide: pane.scrollWidth > pane.clientWidth,
                  spill: panel.scrollWidth - panel.clientWidth,
                  paneRight: pane.getBoundingClientRect().right,
                  panelRight: panel.getBoundingClientRect().right};
        })()"""
    )
    problems = []
    if not box["wide"]:
        problems.append("tour.c's longest C line fits its pane, so the pane check proves nothing")
    if box["spill"] > 0 or box["paneRight"] > box["panelRight"] + 0.5:
        problems.append(f"the C source runs {box['spill']} px past its panel instead of scrolling")
    return problems


def check_stepping_keeps_the_window_still(page: Browser) -> list[str]:
    """Stepping after scrolling down to the drawing leaves the window where it is (round 6)."""
    page.open("#program=sum&cycle=11")
    page.js("window.scrollTo(0, document.documentElement.scrollHeight)")
    before = page.js("window.scrollY")
    if not before:
        return ["the page is too short to scroll, so the stepping check proves nothing"]
    page.step_to(16)
    after = page.js("window.scrollY")
    if after != before:
        return [f"stepping five cycles scrolled the window from y = {before} to {after}"]
    return []


def check_fit_to_height(page: Browser) -> list[str]:
    """*Fit to height* makes a tall block (a 32-bit mux2, 32 gates high) fit its box (round 6)."""
    page.open("#program=sum&cycle=11&view=top.rv.dp.alu.rm.m_and_or")
    measure = """(() => { const v = document.getElementById('view');
                  return [v.querySelector('svg').getBoundingClientRect().height, v.clientHeight];
                })()"""
    tall, box = page.js(measure)
    page.js("document.getElementById('fit-height').click()")
    fitted, box = page.wait_for(
        f"(m => m[0] !== {tall} && m)({measure})", "fit to height to change the drawing"
    )
    problems = []
    if tall <= box:
        problems.append(
            f"the 32-bit mux2 ({tall:.0f} px) fits its box ({box} px) unfitted, "
            "so fit to height proves nothing"
        )
    if fitted > box:
        problems.append(f"fitted to height, the mux2 is {fitted:.0f} px, its box {box} px")
    return problems


def check_explanation_keeps_one_height(page: Browser) -> list[str]:
    """The explanation panel keeps its height while its text changes length (round 6)."""
    page.open("#program=sum&cycle=0")
    seen: dict[int, tuple[float, int]] = {}
    for cycle in range(12):
        page.step_to(cycle)
        seen[cycle] = tuple(
            page.js(
                """(() => { const b = document.getElementById('explain-body');
                            return [b.getBoundingClientRect().height, b.textContent.length]; })()"""
            )
        )
    heights = {round(h, 1) for h, _ in seen.values()}
    lengths = {n for _, n in seen.values()}
    problems = []
    if len(lengths) < 2:
        problems.append("every explanation has the same length, so the height check proves nothing")
    if len(heights) != 1:
        problems.append(
            f"the explanation panel changes height between cycles: {sorted(heights)} px"
        )
    return problems


def check_changed_wires_are_gold(page: Browser) -> list[str]:
    """A wire that changed this cycle has a wide gold band, as the legend shows (round 6)."""
    page.open("#program=sum&cycle=11")
    seen = page.js(
        """(() => {
          const halo = document.querySelector('#view svg.netview .wire-halo');
          if (!halo) return null;
          const probe = document.createElement('span');
          probe.style.color = 'var(--changed)';
          document.body.append(probe);
          const gold = getComputedStyle(probe).color;
          probe.remove();
          const s = getComputedStyle(halo);
          return {stroke: s.stroke, gold, width: parseFloat(s.strokeWidth),
                  shown: s.display !== 'none'};
        })()"""
    )
    if seen is None:
        return ["no changed wire is highlighted in cycle 11"]
    problems = []
    if seen["stroke"] != seen["gold"]:
        problems.append(
            f"a changed wire's band is {seen['stroke']}, not the legend's {seen['gold']}"
        )
    if seen["width"] < 3 or not seen["shown"]:
        problems.append(
            f"a changed wire's band is {seen['width']} px wide (shown: {seen['shown']})"
        )
    return problems


def check_editor(page: Browser, source: str, a0_line: str, rejected: str) -> list[str]:
    """Type a program, press *build and run*, and see it shown; a rejected one keeps the old.

    ``a0_line`` is a line of ``source`` the C pane must then show; ``rejected``
    is a program the backend refuses.
    """
    page.open("#program=sum&cycle=0")
    problems = []
    type_and_run = """(source => {
        document.getElementById('edit').click();
        document.getElementById('source').value = source;
        document.getElementById('run').click();
      })(%s)"""
    page.js(type_and_run % json.dumps(source))
    drawn = page.wait_for(
        "(d => d.startsWith('u_') && d)(document.getElementById('view').dataset.drawn ?? '')",
        "the typed program to be built and drawn",
    )
    shown = page.js("[...document.querySelectorAll('#c-lines li')].map(li => li.textContent)")
    if a0_line not in [line.strip() for line in shown]:
        problems.append(
            f"after build and run, the C pane shows {shown[:2]}..., not the typed program"
        )
    if page.js("document.getElementById('program-pick').selectedOptions[0]?.textContent") != (
        "your program"
    ):
        problems.append("after build and run, the picker does not say 'your program'")
    page.js(type_and_run % json.dumps(rejected))
    message = page.wait_for(
        "(e => !e.hidden && e.textContent)(document.getElementById('build-error'))",
        "the rejected program's message",
    )
    if page.drawn() != drawn:
        problems.append("a rejected program replaced the program on screen")
    if not message.strip():
        problems.append("a rejected program gave no message")
    return problems
