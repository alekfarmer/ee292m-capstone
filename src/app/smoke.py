"""Smoke check against the running app: a real result, not just a status code."""

import json
import sys
import urllib.request

from app.pagecheck import check_first_screen, check_rendered_page

BASE = "http://127.0.0.1:8000"


def fetch(path: str) -> object:
    """GET ``path`` from the app and decode its JSON body."""
    with urllib.request.urlopen(BASE + path, timeout=10) as resp:  # noqa: S310 - fixed URL
        return json.load(resp)


def main() -> int:
    """Check the adder, Spike and trace results; return the exit status."""
    view = fetch("/api/adder/5_plus_3")
    golden = fetch("/api/golden")
    trace = fetch("/api/trace")
    if not (isinstance(view, dict) and isinstance(golden, dict) and isinstance(trace, dict)):
        print("smoke: FAIL: unexpected response shape", file=sys.stderr)
        return 1
    problems = []
    if trace.get("cycles") != golden.get("retired"):
        problems.append(f"trace has {trace.get('cycles')} cycles, Spike {golden.get('retired')}")
    if view.get("sum") != "0x00000008" or view.get("cout") != 0:
        problems.append(f"adder 5 + 3 gave sum={view.get('sum')} cout={view.get('cout')}")
    if "<svg" not in str(view.get("svg", "")):
        problems.append("adder view has no SVG")
    if golden.get("a0_at_halt") != "0x00000037":
        problems.append(f"Spike a0 at halt is {golden.get('a0_at_halt')}, expected 0x00000037")
    with urllib.request.urlopen(BASE + "/", timeout=10) as resp:  # noqa: S310 - fixed URL
        if b"<title>" not in resp.read():
            problems.append("page did not load")
    problems.extend(check_rendered_page())
    start = fetch("/api/start")
    opening = fetch(f"/api/cycle/{start['cycle']}") if isinstance(start, dict) else None
    if not isinstance(opening, dict) or opening.get("c_line") is None:
        problems.append(f"the start cycle {start} is not on a line of C")
        opening = {"cycle": None}
    else:
        problems.extend(
            check_first_screen(opening["cycle"], opening["asm_index"], opening["c_line"])
        )
    for p in problems:
        print(f"smoke: FAIL: {p}", file=sys.stderr)
    if not problems:
        print(
            "smoke: ok (5 + 3 = 0x00000008 on the gates, a0 = 55 in Spike, "
            f"{trace['cycles']}-cycle trace, page renders the datapath with pc = 0x80000000 "
            f"and opens on cycle {opening['cycle']} with its C line lit)"
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
