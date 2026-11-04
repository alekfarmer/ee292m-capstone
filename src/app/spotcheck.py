"""M4 spot-check: every bit the page can show is right, in every cycle.

``make spot-check`` (part of ``make verify``) asks the pipeline for every
view of every program in every cycle, exactly as the API serves them, and
checks each one against the trace and against the logic itself:

1. **Wires.** Every drawn wire carries the trace's value (slices and
   constants included), and ``changed`` says whether it differs from the
   cycle before.
2. **Gates.** Every drawn gate computes its function from its drawn inputs;
   a flip-flop's output is its input of the cycle before.
3. **Adder drawings.** Every wire drawn in a full adder carries the trace's
   value.
4. **Register table.** Each register holds the trace's value, the read
   ports return the registers they select, and a stored value is there in
   the next cycle.
5. **Units.** The outputs of every instance of a datapath unit (adders,
   shifters, multiplexers, the ALU, the load/store unit, the immediate
   decoder, the PC register) equal an independent model of what that unit
   must compute, written here from the RV32I specification, applied to the
   unit's inputs in the trace.

Checks 1-4 show the page draws the verified run faithfully. Check 5 catches
a design that is wrong in the same way at gate level and in RTL, when Spike,
which compares only the PC, the instruction and register writes, sees
nothing (a wrong shifter output that no instruction of the program uses).

Run as ``python -m app.spotcheck [program ...]`` (all programs by default).
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app import hardware, pipeline
from app.models import ModuleView, TraceArtifact
from app.paths import ARTIFACTS_DIR

Cycle = dict[str, int]
Ports = dict[str, int]
M32 = 0xFFFF_FFFF
SHOWN = 12  # problems printed per program; the count says how many there were


@dataclass
class Report:
    """What one program's spot-check looked at, and what it found wrong."""

    program: str
    cycles: int = 0
    views: int = 0
    wires: int = 0
    gates: int = 0
    unit_outputs: int = 0
    unmodelled: set[str] = field(default_factory=set)
    problems: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        """Record one problem."""
        self.problems.append(message)

    def summary(self) -> str:
        """One line: what was checked and whether it all matched."""
        per_cycle = self.views // max(self.cycles, 1)
        head = (
            f"spot-check: {self.program}: {self.cycles} cycles x {per_cycle} views: "
            f"{self.wires} wires, {self.gates} gates, {self.unit_outputs} unit outputs"
        )
        if self.unmodelled:
            head += f" (no unit model, so left to Spike: {', '.join(sorted(self.unmodelled))})"
        if not self.problems:
            return f"{head}; all match"
        shown = "\n  ".join(self.problems[:SHOWN])
        more = (
            f"\n  ... and {len(self.problems) - SHOWN} more" if len(self.problems) > SHOWN else ""
        )
        return f"{head}; {len(self.problems)} PROBLEMS:\n  {shown}{more}"


def decode(trace: TraceArtifact) -> list[Cycle]:
    """Every signal's value in every cycle, expanded here from the change list."""
    names = [s.name for s in trace.signals]
    current = {n: int(v, 16) for n, v in zip(names, trace.initial, strict=True)}
    cycles = [dict(current)]
    for changes in trace.changes:
        for i, v in changes:
            current[names[i]] = int(v, 16)
        cycles.append(dict(current))
    return cycles


def _bits(value: int, lo: int, width: int) -> int:
    return (value >> lo) & ((1 << width) - 1)


def _signed(value: int) -> int:
    return value - (1 << 32) if value & 0x8000_0000 else value


def _sext(value: int, width: int) -> int:
    """Sign-extend the ``width``-bit ``value`` to 32 bits."""
    sign = 1 << (width - 1)
    return ((value ^ sign) - sign) & M32


# --- 1. wires ----------------------------------------------------------------------


def _constant(label: str) -> int:
    """The value of a drawn constant: ``32'h4``, or ``0``/``1`` for one bit."""
    return int(label.split("'h", 1)[1], 16) if "'h" in label else int(label)


def check_wires(view: ModuleView, cycles: list[Cycle], n: int, report: Report) -> None:
    """Check 1: every wire's drawn value and ``changed`` flag against the trace."""
    for e in view.edges:
        report.wires += 1
        where = f"cycle {n} {view.path}: wire {e.net} into {e.target}.{e.target_port}"
        drawn = int(e.value, 16)
        if e.signal is None:
            if drawn != _constant(e.net):
                report.fail(f"{where} shows {e.value}, but the constant is {e.net}")
            continue
        if e.signal not in cycles[n]:
            report.fail(f"{where}: {e.signal} is not in the trace")
            continue
        want = _bits(cycles[n][e.signal], e.lo, e.width)
        if drawn != want:
            report.fail(f"{where} shows {e.value}, the trace has {want:#x}")
        before = _bits(cycles[n - 1][e.signal], e.lo, e.width) if n > 0 else want
        if e.changed != (before != want):
            report.fail(f"{where} is marked changed={e.changed}, but it was {before:#x}")


# --- 2. gates ----------------------------------------------------------------------

GATE_FUNCTIONS: dict[str, Callable[[Ports], int]] = {
    "AND": lambda p: p["A"] & p["B"],
    "OR": lambda p: p["A"] | p["B"],
    "XOR": lambda p: p["A"] ^ p["B"],
    "NOT": lambda p: 1 - p["A"],
    "MUX": lambda p: p["B"] if p["S"] else p["A"],  # Yosys $_MUX_: S selects B
}


def check_gates(view: ModuleView, cycles: list[Cycle], n: int, report: Report) -> None:
    """Check 2: each drawn gate's output follows from its drawn inputs."""
    gates = {node.id: node for node in view.nodes if node.kind == "gate"}
    inputs: dict[str, Ports] = {g: {} for g in gates}
    d_wire: dict[str, tuple[str | None, int]] = {}
    outputs: dict[str, set[int]] = {g: set() for g in gates}
    for e in view.edges:
        if e.target in gates:
            inputs[e.target][e.target_port] = int(e.value, 16)
            if e.target_port == "D":
                d_wire[e.target] = (e.signal, e.lo)
        if e.source in gates:
            outputs[e.source].add(int(e.value, 16))
    for gate_id, node in gates.items():
        report.gates += 1
        where = f"cycle {n} {view.path}: {node.label} gate {gate_id}"
        drawn = outputs[gate_id]
        if len(drawn) != 1:
            report.fail(f"{where}: its output is drawn as {sorted(drawn) or 'nothing'}")
            continue
        (out,) = drawn
        if node.label == "DFF":
            if n == 0:
                continue  # the value before the first cycle is the reset's, not in the trace
            signal, lo = d_wire.get(gate_id, (None, 0))
            want = _bits(cycles[n - 1][signal], lo, 1) if signal else inputs[gate_id].get("D")
        else:
            try:
                want = GATE_FUNCTIONS[node.label](inputs[gate_id])
            except KeyError as exc:
                report.fail(f"{where}: input {exc} is not drawn")
                continue
        if out != want:
            report.fail(f"{where} outputs {out} from inputs {inputs[gate_id]}, should be {want}")


# --- 3. the adder drawing ------------------------------------------------------------


def check_adder(
    view: ModuleView, netlist: hardware.Netlist, cycles: list[Cycle], n: int, report: Report
) -> None:
    """Check 3: every full-adder wire in the drawing carries the trace's value."""
    prefix = view.path.removeprefix("top.") + "."
    cells = [c.lstrip("\\") for c in hardware.full_adder_order(netlist)]
    seen = 0
    # The SVG is our own renderer's output (render.py), not outside input.
    for el in ET.fromstring(view.svg or "<svg/>").iter():  # noqa: S314
        net, bit = el.get("data-net"), el.get("data-bit")
        if net is None or bit is None or "wire" not in (el.get("class") or "").split():
            continue
        seen += 1
        report.wires += 1
        signal = f"{prefix}{cells[int(bit)]}.{net}"
        drawn, want = int(el.get("data-value", "-1")), cycles[n].get(signal)
        if drawn != want:
            report.fail(f"cycle {n} {view.path}: bit {bit} wire {net} drawn {drawn}, trace {want}")
    if seen == 0:
        report.fail(f"cycle {n} {view.path}: the adder drawing has no wires")


# --- 4. the register table -------------------------------------------------------------


def check_registers(view: ModuleView, cycles: list[Cycle], n: int, report: Report) -> None:
    """Check 4: the table agrees with the trace and with what the ports read and write."""
    prefix = view.path.removeprefix("top.") + "."
    rows = view.registers or []
    where = f"cycle {n} {view.path}"
    if [r.index for r in rows] != list(range(32)):
        report.fail(f"{where}: the table does not list x0..x31 in order")
        return
    c = cycles[n]
    port = {p: c[prefix + p] for p in ("a1", "a2", "a3", "we3", "wd3", "rd1", "rd2")}
    for r in rows:
        report.wires += 1
        value = int(r.value, 16)
        stored = c.get(f"{prefix}rf[{r.index}]")
        if r.index == 0 and value != 0:
            report.fail(f"{where}: x0 holds {r.value}")
        if stored is not None and value != stored:
            report.fail(f"{where}: x{r.index} shown as {r.value}, the trace has {stored:#010x}")
        if stored is None and value != 0:
            report.fail(f"{where}: x{r.index} shown as {r.value}, but it is never written")
        for read, addr in (("rd1", "a1"), ("rd2", "a2")):
            selected = port[addr] == r.index
            if (read in r.read_by) != selected:
                report.fail(f"{where}: x{r.index} read_by {r.read_by}, but {addr}={port[addr]}")
            if selected and port[read] != value:
                report.fail(f"{where}: {read} reads {port[read]:#x}, x{r.index} holds {r.value}")
        writes = port["we3"] == 1 and port["a3"] == r.index and r.index != 0
        if (r.written is not None) != writes:
            report.fail(f"{where}: x{r.index} written={r.written}, we3={port['we3']}")
        if writes and r.written is not None:
            if int(r.written, 16) != port["wd3"]:
                report.fail(f"{where}: x{r.index} stores {r.written}, wd3={port['wd3']:#x}")
            after = cycles[n + 1].get(f"{prefix}rf[{r.index}]") if n + 1 < len(cycles) else None
            if n + 1 < len(cycles) and after != port["wd3"]:
                report.fail(f"cycle {n + 1} {view.path}: x{r.index} holds {after}, not the store")


# --- 5. the units, against an independent model -----------------------------------------


def _shift_right(a: int, shamt: int, fill: int) -> int:
    ones = (M32 << (32 - shamt)) & M32 if fill else 0
    return (a >> shamt) | ones


def _add(a: int, b: int, cin: int) -> tuple[int, int]:
    total = a + b + cin
    return total & M32, total >> 32


SUBTRACTS = {1, 5, 6}  # sub, slt, sltu


def _alu(p: Ports) -> Ports:
    """RV32I ALU: alucontrol 0 add 1 sub 2 and 3 or 4 xor 5 slt 6 sltu 7 sll 8 srl 9 sra."""
    a, b, op = p["a"], p["b"], p["alucontrol"]
    sub = int(op in SUBTRACTS)
    b_eff = b ^ M32 if sub else b
    s, carry = _add(a, b_eff, sub)
    sh = b & 31
    results = {
        0: s,
        1: s,
        2: a & b,
        3: a | b,
        4: a ^ b,
        5: int(_signed(a) < _signed(b)),
        6: int(a < b),
        7: (a << sh) & M32,
        8: a >> sh,
        9: (_signed(a) >> sh) & M32,
    }
    if op not in results:
        raise ValueError(f"alucontrol = {op:#06b}, a code aludec never produces")
    overflow = (a >> 31) == (b_eff >> 31) and (s >> 31) != (a >> 31)
    return {
        "result": results[op],
        "zero": int(s == 0),
        "neg": s >> 31,
        "ovf": int(overflow),
        "carry": carry,
    }


def _resultmux(p: Ports) -> Ports:
    op = p["alucontrol"]
    by_code = {
        0: p["sum"],
        1: p["sum"],
        2: p["y_and"],
        3: p["y_or"],
        4: p["y_xor"],
        5: p["lt"],
        6: p["ltu"],
        7: p["y_sll"],
        8: p["y_srl"],
        9: p["y_sra"],
    }
    if op not in by_code:
        raise ValueError(f"alucontrol = {op:#06b}, a code aludec never produces")
    return {"result": by_code[op]}


def _lanes(size: int, offset: int, data: int) -> Ports:
    """Store data in its byte lanes: size 0 byte, 1 halfword, 2 or 3 word."""
    if size == 0:
        return {"writedata": (data & 0xFF) * 0x0101_0101, "byteen": 1 << offset}
    if size == 1:
        return {"writedata": (data & 0xFFFF) * 0x0001_0001, "byteen": 0b11 << (offset & 2)}
    return {"writedata": data, "byteen": 0b1111}


def _load(funct3: int, aligned: int) -> int:
    """Lb lh lw lbu lhu (funct3 0 1 2 4 5) of a word already shifted to bit 0."""
    size, unsigned = funct3 & 3, funct3 & 4
    if size == 0:
        return aligned & 0xFF if unsigned else _sext(aligned & 0xFF, 8)
    if size == 1:
        return aligned & 0xFFFF if unsigned else _sext(aligned & 0xFFFF, 16)
    return aligned


def _immediate(p: Ports) -> Ports:
    """The RV32I immediate of each format (immsrc 0 I, 1 S, 2 B, 3 J, 4 U)."""
    i = p["instr"] << 7  # the port holds instr[31:7]

    def f(hi: int, lo: int) -> int:
        return _bits(i, lo, hi - lo + 1)

    formats = {
        0: _sext(f(31, 20), 12),
        1: _sext(f(31, 25) << 5 | f(11, 7), 12),
        2: _sext(f(31, 31) << 12 | f(7, 7) << 11 | f(30, 25) << 5 | f(11, 8) << 1, 13),
        3: _sext(f(31, 31) << 20 | f(19, 12) << 12 | f(20, 20) << 11 | f(30, 21) << 1, 21),
        4: i & 0xFFFF_F000,
    }
    return {"immext": formats.get(p["immsrc"], 0)}


Model = Callable[[Ports], Ports]

# What each unit must compute, from its input ports.
MODELS: dict[str, Model] = {
    "full_adder": lambda p: {
        "s": p["a"] ^ p["b"] ^ p["cin"],
        "cout": int(p["a"] + p["b"] + p["cin"] >= 2),
    },
    "adder32": lambda p: dict(zip(("s", "cout"), _add(p["a"], p["b"], p["cin"]), strict=True)),
    "binvert": lambda p: {"y": p["b"] ^ M32 if p["invert"] else p["b"]},
    "zerodetect": lambda p: {"zero": int(p["a"] == 0)},
    "logicunit": lambda p: {
        "y_and": p["a"] & p["b"],
        "y_or": p["a"] | p["b"],
        "y_xor": p["a"] ^ p["b"],
    },
    "mux2": lambda p: {"y": p["d1"] if p["s"] else p["d0"]},
    "mux3": lambda p: {"y": p["d2"] if p["s"] & 2 else p["d1"] if p["s"] & 1 else p["d0"]},
    "shiftleft": lambda p: {"y": (p["a"] << p["shamt"]) & M32},
    "shiftright": lambda p: {"y": _shift_right(p["a"], p["shamt"], p["fill"])},
    "shifter": lambda p: {
        "y_sll": (p["a"] << p["shamt"]) & M32,
        "y_srl": p["a"] >> p["shamt"],
        "y_sra": (_signed(p["a"]) >> p["shamt"]) & M32,
    },
    "resultmux": _resultmux,
    "alu": _alu,
    "storealign": lambda p: _lanes(p["size"], p["offset"], p["storedata"]),
    "loadalign": lambda p: {"aligned": p["readword"] >> (8 * p["offset"])},
    "loadextend": lambda p: {"loaddata": _load(p["funct3"], p["aligned"])},
    "lsu": lambda p: {
        **_lanes(p["funct3"] & 3, p["offset"], p["storedata"]),
        "loaddata": _load(p["funct3"], p["readword"] >> (8 * p["offset"])),
    },
    "extend": _immediate,
}
PC_RESET = 0x8000_0000  # flopr's reset value: the start of RAM


def instances(netlist: hardware.Netlist) -> list[tuple[str, str]]:
    """``(prefix, module)`` of every module instance under ``top``.

    For example ``("rv.dp.alu.", "alu")``.
    """
    modules = netlist["modules"]
    found: list[tuple[str, str]] = []

    def walk(module: str, prefix: str) -> None:
        for name, cell in modules[module].get("cells", {}).items():
            if cell["type"] in modules:
                child = f"{prefix}{name.lstrip(chr(92))}."
                found.append((child, cell["type"]))
                walk(cell["type"], child)

    walk("top", "")
    return found


def check_units(
    netlist: hardware.Netlist,
    cycles: list[Cycle],
    report: Report,
    only_cycles: list[int] | None = None,
) -> None:
    """Check 5: every modelled unit's outputs equal the model's (in ``only_cycles``, or all)."""
    chosen = range(len(cycles)) if only_cycles is None else only_cycles
    modules: dict[str, Any] = netlist["modules"]
    for prefix, module in instances(netlist):
        ports = modules[module]["ports"]
        ins = [p for p, d in ports.items() if d["direction"] == "input"]
        outs = [p for p, d in ports.items() if d["direction"] == "output"]
        if module == "flopr":
            for n in (k for k in chosen if k > 0):
                before, now = cycles[n - 1], cycles[n]
                q = PC_RESET if before[prefix + "reset"] else before[prefix + "d"]
                report.unit_outputs += 1
                if now[prefix + "q"] != q:
                    report.fail(f"cycle {n} {prefix}q = {now[prefix + 'q']:#x}, should be {q:#x}")
            continue
        model = MODELS.get(module)
        if model is None:
            # Only modules with gates of their own need a model; the others
            # (datapath, ...) are wiring between modelled units.
            own_gates = any(
                c["type"] in hardware.GATE_TYPES for c in modules[module]["cells"].values()
            )
            if own_gates:
                report.unmodelled.add(module)
            continue
        for n in chosen:
            c = cycles[n]
            try:
                want = model({p: c[prefix + p] for p in ins if p != "clk"})
            except (KeyError, ValueError) as exc:
                report.fail(f"cycle {n} {prefix[:-1]} ({module}): {exc}")
                continue
            for out in outs:
                report.unit_outputs += 1
                got = c.get(prefix + out)
                if got != want[out]:
                    shown = "missing" if got is None else f"{got:#x}"
                    report.fail(
                        f"cycle {n} {prefix}{out} ({module}) is {shown}, "
                        f"should be {want[out]:#x} from {_show_inputs(c, prefix, ins)}"
                    )


def _show_inputs(c: Cycle, prefix: str, ins: list[str]) -> str:
    return ", ".join(f"{p}={c[prefix + p]:#x}" for p in ins if prefix + p in c)


# --- running ---------------------------------------------------------------------------


def check_program(
    program: str, art_dir: Path = ARTIFACTS_DIR, only_cycles: list[int] | None = None
) -> Report:
    """Run every check on one program (on ``only_cycles`` if given, else every cycle)."""
    report = Report(program)
    cycles = decode(pipeline.get_trace(art_dir, program))
    netlist = hardware.load_netlist(art_dir / pipeline.NETLIST_FILE)
    chosen = range(len(cycles)) if only_cycles is None else only_cycles
    paths = pipeline.list_view_paths(art_dir)
    for n in chosen:
        report.cycles += 1
        for path in paths:
            view = pipeline.get_module_view(path, n, art_dir, program)
            report.views += 1
            if view.kind == "adder":
                check_adder(view, netlist, cycles, n, report)
            elif view.kind == "registers":
                check_registers(view, cycles, n, report)
            else:
                check_wires(view, cycles, n, report)
                check_gates(view, cycles, n, report)
    check_units(netlist, cycles, report, only_cycles)
    return report


def main(argv: list[str] | None = None) -> int:
    """Check the named programs (all by default); return 1 if anything is wrong."""
    parser = argparse.ArgumentParser(prog="app.spotcheck", description=__doc__)
    parser.add_argument("programs", nargs="*", help="programs to check (default: all)")
    args = parser.parse_args(argv)
    names = args.programs or pipeline.list_programs()
    if not names:
        print("spot-check: no programs have artifacts; run 'make artifacts'")
        return 1
    ok = True
    for name in names:
        report = check_program(name)
        print(report.summary(), flush=True)
        ok = ok and not report.problems
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
