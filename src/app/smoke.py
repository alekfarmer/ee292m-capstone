"""Smoke check against the running app: a real result, not just a status code."""

import argparse
import json
import sys
import urllib.request

from app.pagecheck import check_first_screen, check_rendered_page

DEFAULT_PORT = 8000


def fetch(base: str, path: str) -> object:
    """GET ``path`` from the app at ``base`` and decode its JSON body."""
    with urllib.request.urlopen(base + path, timeout=10) as resp:  # noqa: S310 - local URL
        return json.load(resp)


def check(base: str) -> tuple[list[str], str]:
    """Problems with the app at ``base`` (empty if none), and a summary of what was seen."""
    view = fetch(base, "/api/adder/5_plus_3")
    golden = fetch(base, "/api/golden")
    trace = fetch(base, "/api/trace")
    if not (isinstance(view, dict) and isinstance(golden, dict) and isinstance(trace, dict)):
        return ["unexpected response shape"], ""
    problems = []
    if trace.get("cycles") != golden.get("retired"):
        problems.append(f"trace has {trace.get('cycles')} cycles, Spike {golden.get('retired')}")
    if view.get("sum") != "0x00000008" or view.get("cout") != 0:
        problems.append(f"adder 5 + 3 gave sum={view.get('sum')} cout={view.get('cout')}")
    if "<svg" not in str(view.get("svg", "")):
        problems.append("adder view has no SVG")
    if golden.get("a0_at_halt") != "0x00000037":
        problems.append(f"Spike a0 at halt is {golden.get('a0_at_halt')}, expected 0x00000037")
    with urllib.request.urlopen(base + "/", timeout=10) as resp:  # noqa: S310 - local URL
        if b"<title>" not in resp.read():
            problems.append("page did not load")
    problems.extend(check_rendered_page(base + "/"))
    start = fetch(base, "/api/start")
    opening = fetch(base, f"/api/cycle/{start['cycle']}") if isinstance(start, dict) else None
    if not isinstance(opening, dict) or opening.get("c_line") is None:
        problems.append(f"the start cycle {start} is not on a line of C")
        return problems, ""
    problems.extend(
        check_first_screen(opening["cycle"], opening["asm_index"], opening["c_line"], base + "/")
    )
    summary = (
        "5 + 3 = 0x00000008 on the gates, a0 = 55 in Spike, "
        f"{trace['cycles']}-cycle trace, page renders the datapath with pc = 0x80000000 "
        f"and opens on cycle {opening['cycle']} with its C line lit"
    )
    return problems, summary


def main(argv: list[str] | None = None) -> int:
    """Check the adder, Spike, trace and page results; return the exit status."""
    parser = argparse.ArgumentParser(prog="app.smoke", description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, choices=range(1024, 65536))
    args = parser.parse_args(argv)
    problems, summary = check(f"http://127.0.0.1:{args.port}")
    for p in problems:
        print(f"smoke: FAIL: {p}", file=sys.stderr)
    if not problems:
        print(f"smoke: ok ({summary})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
