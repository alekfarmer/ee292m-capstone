"""Smoke check against the running app: a real result, not just a status code."""

import argparse
import json
import sys
import urllib.request

from app.pagecheck import (
    check_first_screen,
    check_gate_view,
    check_register_table,
    check_rendered_page,
)

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
    problems.extend(_check_halt_store(base, trace.get("cycles")))
    with urllib.request.urlopen(base + "/", timeout=10) as resp:  # noqa: S310 - local URL
        if b"<title>" not in resp.read():
            problems.append("page did not load")
    problems.extend(check_rendered_page(base + "/"))
    start = fetch(base, "/api/start")
    if not isinstance(start, dict) or not isinstance(start.get("cycle"), int):
        problems.append(f"/api/start gave {start}")
        return problems, ""
    opening = fetch(base, f"/api/cycle/{start['cycle']}")
    if not isinstance(opening, dict) or opening.get("c_line") is None:
        problems.append(f"the start cycle {start} is not on a line of C")
        return problems, ""
    problems.extend(
        check_first_screen(
            opening["cycle"], opening["asm_index"], opening["c_line"], start["reason"], base + "/"
        )
    )
    problems.extend(_check_m4_views(base, opening["cycle"]))
    summary = (
        "5 + 3 = 0x00000008 on the gates, a0 = 55 in Spike and in the core's halt store, "
        f"{trace['cycles']}-cycle trace, page renders the datapath with pc = 0x80000000 "
        f"and opens on cycle {opening['cycle']} with its C line lit; a shifter stage "
        "draws its gates and the register table matches the API"
    )
    return problems, summary


def _check_m4_views(base: str, cycle: int) -> list[str]:
    """M4 on the page: a former block-only module draws gates; the register table is right."""
    problems = check_gate_view(f"#cycle={cycle}&view=top.rv.dp.alu.sh.asr.by16", base + "/")
    view = fetch(base, f"/api/view/top.rv.dp.rf?cycle={cycle}")
    rows = view.get("registers") if isinstance(view, dict) else None
    if not isinstance(rows, list) or len(rows) != 32:
        return [*problems, f"/api/view/top.rv.dp.rf gave {str(view)[:80]}"]
    values = {r["index"]: r["value"] for r in rows}
    written = next((r["index"] for r in rows if r["written"] is not None), None)
    problems.extend(check_register_table(cycle, values, written, base + "/"))
    return problems


def _check_halt_store(base: str, cycles: object) -> list[str]:
    """The core's own a0 = 55: its last cycle stores (a0 << 1) | 1 to tohost."""
    if not isinstance(cycles, int) or cycles < 1:
        return [f"trace has {cycles} cycles"]
    top = fetch(base, f"/api/view/top?cycle={cycles - 1}")
    edges = top.get("edges", []) if isinstance(top, dict) else []
    stored = {int(e["value"], 16) for e in edges if e.get("target_port") == "dwdata"}
    if stored != {(55 << 1) | 1}:
        return [
            f"the core's halt store carries {sorted(map(hex, stored))}, expected 0x6f (a0 = 55)"
        ]
    return []


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
