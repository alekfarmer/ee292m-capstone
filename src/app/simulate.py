"""M2: run the program on the whole core, at gate level and at RTL.

Two independent simulations of the same program:

* **Gate level** (what the views show): Yosys ``sim`` on the synthesized
  netlist, with the register file and RAM black boxes replaced by their
  behavioural models.
* **RTL reference**: Icarus Verilog on the SystemVerilog source.

Both are sampled once per clock cycle, just before the rising edge (see
:func:`app.vcd.sample_cycles`). Names are relative to ``top``, e.g.
``rv.dp.alu.result``.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from app.errors import PipelineError
from app.hardware import YOSYS, Netlist, is_blackbox, load_netlist
from app.models import GoldenArtifact
from app.paths import RTL_DIR
from app.tools import run_tool
from app.vcd import Value, read_timeline, sample_cycles

IVERILOG = "iverilog"
VVP = "vvp"
RAM_IMAGE = "ram.hex"  # file name ram.sv reads, in the simulator's working directory
TESTBENCH = RTL_DIR / "tb_rtl.sv"
GATE_PREFIX = "top."
RTL_PREFIX = "tb_rtl.dut."

# Signals (relative to top) the checks read.
PC = "rv.pc"
INSTR = "rv.instr"
RF_WE = "rv.dp.rf.we3"
RF_A1, RF_A2, RF_A3 = "rv.dp.rf.a1", "rv.dp.rf.a2", "rv.dp.rf.a3"
RF_RD1, RF_RD2, RF_WD = "rv.dp.rf.rd1", "rv.dp.rf.rd2", "rv.dp.rf.wd3"
MEM_WE, MEM_ADDR = "mem.dwe", "mem.daddr"


@dataclass(frozen=True)
class SimRun:
    """Per-cycle values of every signal of one simulation."""

    cycles: list[dict[str, Value]]
    widths: dict[str, int]


def rtl_sources() -> list[Path]:
    """Every SystemVerilog file of the core (testbenches excluded)."""
    return sorted(p for p in RTL_DIR.glob("*.sv") if not p.name.startswith("tb_"))


def write_ram_image(words: list[int], work_dir: Path) -> Path:
    """Write the RAM image where ram.sv's ``$readmemh`` finds it."""
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / RAM_IMAGE
    path.write_text("".join(f"{w:08x}\n" for w in words))
    return path


def _strip_widths(widths: dict[str, int], prefix: str) -> dict[str, int]:
    return {k[len(prefix) :]: w for k, w in widths.items() if k.startswith(prefix)}


def blackbox_instances(netlist: Netlist, top: str = "top") -> list[str]:
    """Hierarchical names of the black-box instances (register file, RAM)."""
    modules = netlist["modules"]
    found: list[str] = []

    def walk(module: str, path: str) -> None:
        for cell_name, cell in modules[module].get("cells", {}).items():
            ctype = cell["type"]
            if ctype not in modules:
                continue
            name = cell_name.lstrip("\\")
            child = f"{path}.{name}" if path else name
            if is_blackbox(modules[ctype]):
                found.append(child)
            else:
                walk(ctype, child)

    walk(top, "")
    return sorted(found)


def _is_model_internal(name: str, models: list[str]) -> bool:
    """A private ($-named) net inside a behavioural model, not part of the design."""
    return any(name.startswith(m + ".") and name[len(m) + 1 :].startswith("$") for m in models)


def run_gate_level(netlist_path: Path, words: list[int], n_cycles: int, work_dir: Path) -> SimRun:
    """Simulate the synthesized netlist for ``n_cycles`` cycles after reset.

    The black boxes are replaced by their behavioural models (regfile.sv,
    ram.sv). Their ports and named signals are kept; the private nets Yosys
    creates while lowering those models' processes are dropped, because they
    are simulator scaffolding, not part of the synthesized design.
    """
    write_ram_image(words, work_dir)
    vcd = work_dir / "gate.vcd"
    model_files = " ".join(str(RTL_DIR / f) for f in ("regfile.sv", "ram.sv"))
    script = (
        f"read_json {netlist_path}; "
        f"read_verilog -sv -overwrite -DSIM_RAM_IMAGE {model_files}; "
        "hierarchy -check -top top; "
        "proc regfile ram; memory -nomap regfile ram; "
        f"sim -clock clk -reset reset -rstlen 1 -n {n_cycles + 2} -a -q -vcd {vcd}"
    )
    run_tool([YOSYS, "-q", "-p", script], cwd=work_dir, timeout=600)
    timeline = read_timeline(vcd.read_text())
    cycles = sample_cycles(
        timeline, GATE_PREFIX + "clk", GATE_PREFIX + "reset", strip_prefix=GATE_PREFIX
    )
    model_instances = blackbox_instances(load_netlist(netlist_path))
    widths = {
        k: w
        for k, w in _strip_widths(timeline.widths, GATE_PREFIX).items()
        if not _is_model_internal(k, model_instances)
    }
    kept = [{k: v for k, v in c.items() if k in widths} for c in cycles[:n_cycles]]
    return SimRun(kept, widths)


def run_rtl(words: list[int], n_cycles: int, work_dir: Path) -> SimRun:
    """Simulate the SystemVerilog source with Icarus for ``n_cycles`` cycles."""
    write_ram_image(words, work_dir)
    vvp = work_dir / "rtl.vvp"
    run_tool(
        [
            IVERILOG,
            "-g2012",
            "-DSIM_RAM_IMAGE",
            f"-DCYCLES={n_cycles + 1}",
            "-s",
            "tb_rtl",
            "-o",
            str(vvp),
            *[str(p) for p in rtl_sources()],
            str(TESTBENCH),
        ],
        cwd=work_dir,
    )
    run_tool([VVP, "-n", str(vvp)], cwd=work_dir, timeout=600)
    timeline = read_timeline((work_dir / "rtl.vcd").read_text())
    cycles = sample_cycles(
        timeline, RTL_PREFIX + "clk", RTL_PREFIX + "reset", strip_prefix=RTL_PREFIX
    )
    return SimRun(cycles[:n_cycles], _strip_widths(timeline.widths, RTL_PREFIX))


# --- checks --------------------------------------------------------------------


def port_paths(netlist: Netlist, top: str = "top") -> list[str]:
    """The hierarchical name of every port of every module instance under ``top``."""
    modules = netlist["modules"]

    def walk(module: str, path: str) -> Iterator[str]:
        prefix = f"{path}." if path else ""
        for port in modules[module]["ports"]:
            yield prefix + port
        for cell_name, cell in modules[module].get("cells", {}).items():
            if cell["type"] in modules:
                yield from walk(cell["type"], prefix + cell_name.lstrip("\\"))

    return sorted(walk(top, ""))


def halt_cycle(run: SimRun, tohost: int) -> int:
    """The first cycle that stores to ``tohost`` (the program's halt).

    Raises:
        PipelineError: the core never halts in the simulated cycles.
    """
    for n, c in enumerate(run.cycles):
        if c.get(MEM_WE) == 1 and c.get(MEM_ADDR) == tohost:
            return n
    raise PipelineError(f"the core did not store to tohost within {len(run.cycles)} cycles")


def compared_signals(gate: SimRun, rtl: SimRun, netlist: Netlist) -> list[str]:
    """Signals present in both runs with the same width; must include every port.

    Raises:
        PipelineError: a port is missing from either run or differs in width.
    """
    common = sorted(
        n for n, w in gate.widths.items() if rtl.widths.get(n) == w and n in gate.cycles[0]
    )
    missing = sorted(set(port_paths(netlist)) - set(common))
    if missing:
        raise PipelineError(
            f"{len(missing)} ports cannot be compared between gate level and RTL, "
            f"e.g. {', '.join(missing[:5])}"
        )
    return common


def compare_runs(gate: SimRun, rtl: SimRun, names: list[str], n_cycles: int) -> None:
    """Require gate level and RTL to agree on ``names`` in every cycle.

    Raises:
        PipelineError: naming the first cycle and signals that differ.
    """
    if len(gate.cycles) < n_cycles or len(rtl.cycles) < n_cycles:
        raise PipelineError("a simulation produced fewer cycles than requested")
    for n in range(n_cycles):
        g, r = gate.cycles[n], rtl.cycles[n]
        diff = [s for s in names if g.get(s) != r.get(s)]
        if diff:
            shown = ", ".join(f"{s}: gate={g.get(s)} rtl={r.get(s)}" for s in diff[:4])
            raise PipelineError(
                f"gate level and RTL differ in cycle {n} on {len(diff)} signals: {shown}"
            )


def check_defined(run: SimRun, n_cycles: int) -> None:
    """Require every signal to be 0/1 (no x or z) in every cycle.

    Raises:
        PipelineError: naming the first cycle and signals with unknown values.
    """
    for n in range(n_cycles):
        unknown = sorted(k for k, v in run.cycles[n].items() if v is None)
        if unknown:
            raise PipelineError(
                f"cycle {n}: {len(unknown)} signals are x/z, e.g. {', '.join(unknown[:5])}"
            )


def check_against_golden(run: SimRun, golden: GoldenArtifact) -> int:
    """Require PC, instruction and register writes to match Spike every cycle.

    Returns:
        The number of register writes checked.

    Raises:
        PipelineError: naming the first cycle that differs.
    """
    writes = 0
    for n, entry in enumerate(golden.entries):
        c = run.cycles[n]
        pc, insn = int(entry.pc, 16), int(entry.insn, 16)
        if c[PC] != pc or c[INSTR] != insn:
            raise PipelineError(
                f"cycle {n}: hardware is at pc=0x{c[PC] or 0:08x} insn=0x{c[INSTR] or 0:08x}, "
                f"Spike at pc={entry.pc} insn={entry.insn}"
            )
        hw_writes = c[RF_WE] == 1 and c[RF_A3] != 0
        if entry.rd not in (None, 0):
            if not hw_writes or c[RF_A3] != entry.rd or c[RF_WD] != int(entry.rd_value or "0", 16):
                raise PipelineError(
                    f"cycle {n} (pc={entry.pc}): Spike writes x{entry.rd}={entry.rd_value}, "
                    f"hardware we={c[RF_WE]} x{c[RF_A3]}=0x{c[RF_WD] or 0:08x}"
                )
            writes += 1
        elif hw_writes:
            raise PipelineError(
                f"cycle {n} (pc={entry.pc}): hardware writes x{c[RF_A3]}, Spike writes nothing"
            )
    return writes


def check_x0(run: SimRun, n_cycles: int) -> None:
    """Require x0 to read as 0 on both register-file read ports in every cycle.

    Raises:
        PipelineError: naming the first cycle where x0 reads non-zero.
    """
    for n in range(n_cycles):
        c = run.cycles[n]
        for addr, data in ((RF_A1, RF_RD1), (RF_A2, RF_RD2)):
            if c[addr] == 0 and c[data] != 0:
                raise PipelineError(f"cycle {n}: x0 reads 0x{c[data] or 0:08x} on {data}")
