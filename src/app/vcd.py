"""Read VCD files written by Yosys ``sim`` and Icarus Verilog.

Signal names are dotted hierarchical paths (``top.rv.dp.pc``). Escaped
identifiers lose their leading backslash, and a scope given as one escaped
name (``g_bit[3].fa``) reads the same as nested scopes (``g_bit[3]`` then
``fa``). A value containing x or z is ``None``.
"""

import re
from dataclasses import dataclass, field

from app.errors import PipelineError

Value = int | None

_VAR = re.compile(r"\$var\s+(\S+)\s+(\d+)\s+(\S+)\s+(\S+)(?:\s+\[[^\]]*\])?\s+\$end")
# VCD variable types that carry logic values (not parameters, events, reals).
_LOGIC_TYPES = {"wire", "reg", "logic", "integer", "tri", "supply0", "supply1", "bit"}


@dataclass
class Timeline:
    """Every signal of a VCD file and every value change, in time order."""

    widths: dict[str, int] = field(default_factory=dict)
    # (time, [(name, value), ...]) in increasing time order.
    steps: list[tuple[int, list[tuple[str, Value]]]] = field(default_factory=list)


def read_timeline(text: str) -> Timeline:
    """Parse a whole VCD file."""
    scopes: list[str] = []
    ids: dict[str, list[str]] = {}
    timeline = Timeline()
    lines = iter(text.splitlines())
    for raw in lines:
        line = raw.strip()
        if line.startswith("$scope"):
            scopes.append(line.split()[2].lstrip("\\"))
        elif line.startswith("$upscope"):
            scopes.pop()
        elif line.startswith("$var"):
            m = _VAR.match(line)
            if not m:
                raise PipelineError(f"cannot parse VCD line: {line}")
            if m.group(1) not in _LOGIC_TYPES:
                continue
            name = ".".join([*scopes, m.group(4).lstrip("\\")])
            ids.setdefault(m.group(3), []).append(name)
            timeline.widths[name] = int(m.group(2))
        elif line.startswith("$enddefinitions"):
            break

    time = 0
    changes: list[tuple[str, Value]] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("$"):
            continue  # $dumpvars / $end wrappers around initial values
        if line[0] == "#":
            if changes:
                timeline.steps.append((time, changes))
                changes = []
            time = int(line[1:])
            continue
        if line[0] in "bB":
            bits, code = line[1:].split()
        elif line[0] in "01xXzZ":
            bits, code = line[0], line[1:]
        else:
            continue  # real-valued changes are not used
        value = None if any(ch in bits for ch in "xXzZ") else int(bits, 2)
        for name in ids.get(code, []):
            changes.append((name, value))
    if changes:
        timeline.steps.append((time, changes))
    return timeline


def final_values(timeline: Timeline) -> dict[str, Value]:
    """The last value of every signal."""
    values: dict[str, Value] = {}
    for _, changes in timeline.steps:
        values.update(changes)
    return values


def sample_cycles(
    timeline: Timeline, clock: str, reset: str, *, strip_prefix: str = ""
) -> list[dict[str, Value]]:
    """Return the settled values of every signal in each clock cycle.

    A cycle's values are those just before its rising clock edge, so they are
    what that edge commits (the register-file write, the next PC). Cycles in
    which ``reset`` is high are left out, so cycle 0 is the first instruction.

    ``strip_prefix`` is removed from the start of every name, so traces from
    different testbenches can be compared (``tb_rtl.dut.`` -> ``""``).
    """
    values: dict[str, Value] = {}
    cycles: list[dict[str, Value]] = []
    for _, changes in timeline.steps:
        rising = any(n == clock and v == 1 for n, v in changes) and values.get(clock) == 0
        if rising and values.get(reset) == 0:
            cycles.append(dict(values))
        values.update(changes)
    if strip_prefix:
        n = len(strip_prefix)
        cycles = [{k[n:]: v for k, v in c.items() if k.startswith(strip_prefix)} for c in cycles]
    return cycles
