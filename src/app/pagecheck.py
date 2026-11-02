"""Load the real page in headless Chromium: screenshots and a rendered-DOM check.

Used by ``make smoke`` (does the drawn page show the right values?) and
``make screenshot``. The app must be running on 127.0.0.1:8000.
"""

import argparse
import re
import sys
from pathlib import Path

from app.paths import BUILD_DIR, REPO_ROOT
from app.tools import run_tool

CHROMIUM = "chromium-headless-shell"
BASE = "http://127.0.0.1:8000/"
BUDGET_MS = 10_000  # virtual time for the page's fetches and the elk layout
_FLAGS = [
    "--no-sandbox",
    "--disable-gpu",
    "--hide-scrollbars",
    f"--virtual-time-budget={BUDGET_MS}",
]

SHOTS = {
    "first-screen": "",
    "datapath-cycle-0": "#cycle=0&view=top.rv.dp",
    "datapath-cycle-11": "#cycle=11&view=top.rv.dp",
    "alu-cycle-11": "#cycle=11&view=top.rv.dp.alu",
    "adder-cycle-11": "#cycle=11&view=top.rv.dp.alu.add",
    "maindec-cycle-11": "#cycle=11&view=top.rv.c.md",
    "pcmux-cycle-11": "#cycle=11&view=top.rv.dp.pcmux",
}


def dump_dom(fragment: str = "", base: str = BASE) -> str:
    """The page's DOM at ``base`` after its scripts have run."""
    proc = run_tool([CHROMIUM, *_FLAGS, "--dump-dom", base + fragment], timeout=120)
    return proc.stdout


def screenshot(fragment: str, out: Path, width: int = 1600, height: int = 1700) -> Path:
    """Save a PNG of the page at ``fragment`` (e.g. ``#cycle=3``)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    run_tool(
        [
            CHROMIUM,
            *_FLAGS,
            f"--window-size={width},{height}",
            f"--screenshot={out}",
            BASE + fragment,
        ],
        timeout=120,
    )
    return out


def check_rendered_page(base: str = BASE) -> list[str]:
    """Problems with the rendered page at cycle 0 (empty list if it is right)."""
    dom = dump_dom("#cycle=0&view=top.rv.dp", base)
    problems = []
    if 'class="netview"' not in dom:
        problems.append("the datapath drawing did not render")
    # The datapath's pc output carries the reset PC in cycle 0.
    wire = re.search(r'<path[^>]*data-signal="rv\.dp\.pc"[^>]*>', dom)
    if not wire or 'data-value="0x80000000"' not in wire.group(0):
        problems.append("the drawn pc wire does not show 0x80000000 in cycle 0")
    if not re.search(
        r'<tr[^>]*class="current"[^>]*data-index="0"|<tr[^>]*data-index="0"[^>]*class="current"',
        dom,
    ):
        problems.append("the first instruction is not highlighted in cycle 0")
    if 'id="error"' in dom and re.search(r'id="error"[^>]*>[^<]+<', dom):
        problems.append("the page shows an error")
    return problems


def _has_tag(dom: str, tag: str, *attrs: str) -> bool:
    """Whether some ``<tag ...>`` in ``dom`` carries every one of ``attrs``."""
    return any(all(a in m for a in attrs) for m in re.findall(rf"<{tag}\b[^>]*>", dom))


def check_first_screen(cycle: int, asm_index: int, c_line: int, base: str = BASE) -> list[str]:
    """Problems with the page opened without a URL fragment (empty list if right).

    It should open on ``cycle``, with its C line and its instruction highlighted.
    """
    dom = dump_dom("", base)
    problems = []
    if f"cycle {cycle} /" not in dom:
        problems.append(f"the page did not open on cycle {cycle}")
    if not _has_tag(dom, "li", f'data-line="{c_line}"', "current"):
        problems.append(f"C line {c_line} is not highlighted on the first screen")
    if not _has_tag(dom, "tr", f'data-index="{asm_index}"', "current"):
        problems.append(f"instruction {asm_index} is not highlighted on the first screen")
    if not re.search(r'id="start-reason"[^>]*>It opened on cycle', dom):
        problems.append("the start-here sentence does not say why it opened there")
    return problems


def main(argv: list[str] | None = None) -> int:
    """``python -m app.pagecheck screenshot`` writes PNGs to backend/build/screenshots/."""
    parser = argparse.ArgumentParser(prog="app.pagecheck", description=__doc__)
    parser.add_argument("command", choices=["screenshot", "check"])
    args = parser.parse_args(argv)
    if args.command == "check":
        problems = check_rendered_page()
        for p in problems:
            print(f"page: FAIL: {p}", file=sys.stderr)
        return 1 if problems else 0
    for name, fragment in SHOTS.items():
        path = screenshot(fragment, BUILD_DIR / "screenshots" / f"{name}.png")
        print(path.relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
