"""Smoke check against the running app: a real result, not just a status code."""

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000"


def fetch(path: str) -> object:
    """GET ``path`` from the app and decode its JSON body."""
    with urllib.request.urlopen(BASE + path, timeout=10) as resp:  # noqa: S310 - fixed URL
        return json.load(resp)


def main() -> int:
    """Check the 5 + 3 adder case and the Spike result; return the exit status."""
    view = fetch("/api/adder/5_plus_3")
    golden = fetch("/api/golden")
    assert isinstance(view, dict) and isinstance(golden, dict)
    problems = []
    if view.get("sum") != "0x00000008" or view.get("cout") != 0:
        problems.append(f"adder 5 + 3 gave sum={view.get('sum')} cout={view.get('cout')}")
    if "<svg" not in str(view.get("svg", "")):
        problems.append("adder view has no SVG")
    if golden.get("a0_at_halt") != "0x00000037":
        problems.append(f"Spike a0 at halt is {golden.get('a0_at_halt')}, expected 0x00000037")
    with urllib.request.urlopen(BASE + "/", timeout=10) as resp:  # noqa: S310 - fixed URL
        if b"<title>" not in resp.read():
            problems.append("page did not load")
    for p in problems:
        print(f"smoke: FAIL: {p}", file=sys.stderr)
    if not problems:
        print("smoke: ok (5 + 3 = 0x00000008 on the gates, a0 = 55 in Spike, page served)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
