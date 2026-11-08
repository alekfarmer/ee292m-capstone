"""Load the real page in headless Chromium: screenshots and a rendered-DOM check.

Used by ``make smoke`` (does the drawn page show the right values?) and
``make screenshot``. The app must be running on 127.0.0.1:8000.
"""

import argparse
import html
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
    "shifter-cycle-55": "#cycle=55&view=top.rv.dp.alu.sh.asr",
    "shift-stage-cycle-55": "#cycle=55&view=top.rv.dp.alu.sh.asr.by16",
    "resultmux-cycle-11": "#cycle=11&view=top.rv.dp.alu.rm",
    "lsu-cycle-11": "#cycle=11&view=top.rv.dp.lsu",
    "registers-cycle-11": "#cycle=11&view=top.rv.dp.rf",
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
    stages = [_attr(g, "data-stage") for g in re.findall(r"<g\b[^>]*data-stage=[^>]*>", dom)]
    if stages != ["IF", "ID", "EX", "MEM", "WB"]:
        problems.append(f"the datapath's stage bands read {stages}, not IF ID EX MEM WB")
    if [_attr(t, "data-index") for t in _current(dom, "tr")] != ["0"]:
        problems.append("the first instruction is not the one highlighted in cycle 0")
    if _text_of(dom, "start-reason"):
        problems.append("a page opened from a link still says why it opened where it did")
    problems.extend(_error_shown(dom))
    return problems


def check_register_table(
    cycle: int, values: dict[int, str], written: int | None, base: str = BASE
) -> list[str]:
    """Problems with the drawn register table in ``cycle`` (empty list if right).

    ``values`` maps register number to the value the API gives; ``written`` is
    the register the API says is stored into at the end of the cycle.
    """
    dom = dump_dom(f"#cycle={cycle}&view=top.rv.dp.rf", base)
    rows = re.findall(r"(<tr\b[^>]*data-register=[^>]*>)(.*?)</tr>", dom, re.S)
    # Read what a viewer reads: the value column's text (register, name, value, ...).
    drawn = {
        int(_attr(tag, "data-register") or "-1"): (
            re.findall(r"<td[^>]*>([^<]*)</td>", body) + [""] * 3
        )[2]
        for tag, body in rows
    }
    problems = []
    if drawn != values:
        wrong = sorted(n for n in set(drawn) | set(values) if drawn.get(n) != values.get(n))
        problems.append(f"the register table shows other values than the API for x{wrong[:4]}")
    lit = [
        int(_attr(tag, "data-register") or "-1")
        for tag, _ in rows
        if "written" in (_attr(tag, "class") or "").split()
    ]
    if lit != ([written] if written is not None else []):
        problems.append(f"the register table marks {lit} as written, the API says {written}")
    problems.extend(_error_shown(dom))
    return problems


def check_gate_view(fragment: str, base: str = BASE) -> list[str]:
    """Problems with a gate-level view: it must draw gates, and no error."""
    dom = dump_dom(fragment, base)
    problems = []
    if not re.search(r'class="node gate', dom):
        problems.append(f"the page at {fragment} draws no gates")
    problems.extend(_error_shown(dom))
    return problems


def _current(dom: str, tag: str) -> list[str]:
    """Every ``<tag ...>`` in ``dom`` whose class list includes ``current``."""
    tags = re.findall(rf"<{tag}\b[^>]*>", dom)
    return [t for t in tags if "current" in (_attr(t, "class") or "").split()]


def _attr(tag: str, name: str) -> str | None:
    """The value of attribute ``name`` in one opening tag, or None."""
    m = re.search(rf'\s{re.escape(name)}="([^"]*)"', tag)
    return m.group(1) if m else None


def _text_of(dom: str, element_id: str) -> str:
    """The text directly inside the element with ``id=element_id`` ("" if none)."""
    m = re.search(rf'id="{re.escape(element_id)}"[^>]*>([^<]*)<', dom)
    return m.group(1).strip() if m else ""


def _error_shown(dom: str) -> list[str]:
    error = _text_of(dom, "error")
    return [f"the page shows an error: {error}"] if error else []


def check_first_screen(
    cycle: int,
    asm_index: int,
    c_line: int,
    reason: str,
    base: str = BASE,
    fragment: str = "",
    source: list[str] | None = None,
) -> list[str]:
    """Problems with the page opened without a cycle in the URL (empty list if right).

    It should open on ``cycle`` with exactly its C line and its instruction
    highlighted, and say why, in the backend's words (``reason``).
    ``fragment`` may name a program (``#program=...``); ``source``, if given,
    is the program's C lines, which the C pane must show in order.
    """
    dom = dump_dom(fragment, base)
    problems = []
    if source is not None:
        shown = [
            html.unescape(t) for t in re.findall(r"<li\b[^>]*data-line=[^>]*>([^<]*)</li>", dom)
        ]
        if [s.strip() for s in shown] != [s.strip() for s in source]:
            problems.append(f"the C pane shows {shown[:3]}..., not the program's source")
    if f"cycle {cycle} /" not in dom:
        problems.append(f"the page did not open on cycle {cycle}")
    lit_lines = [_attr(t, "data-line") for t in _current(dom, "li")]
    if lit_lines != [str(c_line)]:
        problems.append(f"C line {c_line} should be the one highlighted, not {lit_lines}")
    lit_rows = [_attr(t, "data-index") for t in _current(dom, "tr")]
    if lit_rows != [str(asm_index)]:
        problems.append(f"instruction {asm_index} should be the one highlighted, not {lit_rows}")
    said = _text_of(dom, "start-reason")
    if said != f"It opened on cycle {cycle}, {reason}.":
        problems.append(f"the start-here sentence says {said!r}")
    problems.extend(_error_shown(dom))
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
