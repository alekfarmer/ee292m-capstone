"""Pipeline entry points.

Building (offline, ``make artifacts``):
    :func:`build_hardware_artifacts`  M0: netlist, gate counts, adder values
    :func:`build_program_artifacts`   M1: program listing, hex image, Spike log
    :func:`build_trace_artifacts`     M2: verified gate-level trace

Artifact layout: the hardware artifacts (netlist, gate counts, adder values,
toolchain) sit in ``backend/artifacts/``; each program's artifacts (listing,
hex image, Spike log, trace) sit in their own folder named after the program,
e.g. ``backend/artifacts/sum/``, so programs never overwrite each other.

Serving (one function per API endpoint): ``get_*`` read the committed
artifacts and return typed results; nothing is recomputed per request except
the drawings of already-computed values.
"""

import json
import platform
import re
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app import hardware, render, simulate, software, views
from app.errors import ArtifactMissingError, PipelineError
from app.models import (
    AdderCaseInfo,
    AdderValuesArtifact,
    AdderView,
    CycleView,
    GateCountReport,
    GoldenArtifact,
    ModuleView,
    ProgramArtifact,
    SourceLine,
    TraceArtifact,
    TraceSignal,
    TraceVerification,
)
from app.paths import ARTIFACTS_DIR, BUILD_DIR, PROGRAMS_DIR, SUM_PROGRAM
from app.tools import run_tool

NETLIST_FILE = "netlist.json"
GATE_COUNTS_FILE = "gate_counts.json"
ADDER_VALUES_FILE = "adder_values.json"
PROGRAM_FILE = "program.json"
GOLDEN_FILE = "golden.json"
TOOLCHAIN_FILE = "toolchain.json"
TRACE_FILE = "trace.json"
EXTRA_CYCLES = 8  # simulate past Spike's halt, so a late halt is caught too
DEFAULT_PROGRAM = SUM_PROGRAM.stem  # "sum"
PROGRAM_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

ADDER_CASES = [
    hardware.AdderCase("5_plus_3", "5 + 3", 5, 3, 0),
    hardware.AdderCase("ffffffff_plus_1", "0xFFFFFFFF + 1", 0xFFFF_FFFF, 1, 0),
]


def _write_model(model: BaseModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2) + "\n")


# --- building ------------------------------------------------------------------


def build_hardware_artifacts(
    out_dir: Path = ARTIFACTS_DIR, work_dir: Path = BUILD_DIR / "hardware"
) -> GateCountReport:
    """M0: synthesize the core, report gate counts, evaluate the adder cases."""
    netlist_path = out_dir / NETLIST_FILE
    netlist = hardware.synthesize(netlist_path)
    report = hardware.gate_counts(netlist)
    _write_model(report, out_dir / GATE_COUNTS_FILE)
    values = hardware.simulate_adder(netlist_path, ADDER_CASES, work_dir)
    _write_model(values, out_dir / ADDER_VALUES_FILE)
    return report


def build_program_artifacts(
    c_file: Path = SUM_PROGRAM,
    out_dir: Path = ARTIFACTS_DIR,
    work_dir: Path = BUILD_DIR / "software",
) -> tuple[ProgramArtifact, GoldenArtifact]:
    """M1: compile ``c_file``; write program.json, the hex image and golden.json.

    They go in ``out_dir / <program name>/``, the name being the file's stem.

    Raises:
        ProgramRejectedError: the program is outside the subset or does not halt.
        ValueError: the file name is not a valid program name.
    """
    name = c_file.stem
    if not PROGRAM_NAME.match(name):
        raise ValueError(f"program name '{name}' must match {PROGRAM_NAME.pattern}")
    work_dir = work_dir / name
    program = software.compile_program(c_file, work_dir)
    asm = software.disassemble(program)
    words = software.memory_image(program, work_dir)
    image_name = f"{name}.hex"
    golden = software.run_spike(program)

    prog_dir = out_dir / name
    prog_dir.mkdir(parents=True, exist_ok=True)
    (prog_dir / image_name).write_text(software.format_hex_image(words))
    listing = ProgramArtifact(
        source_file=c_file.name,
        c_lines=[
            SourceLine(line=n, text=t)
            for n, t in enumerate(c_file.read_text().splitlines(), start=1)
        ],
        asm=asm,
        compile_flags=software.COMPILE_FLAGS,
        ram_base=f"0x{software.RAM_BASE:08x}",
        ram_size_bytes=software.RAM_SIZE,
        entry=f"0x{program.entry:08x}",
        tohost=f"0x{program.tohost:08x}",
        image_file=image_name,
    )
    _write_model(listing, prog_dir / PROGRAM_FILE)
    _write_model(golden, prog_dir / GOLDEN_FILE)
    return listing, golden


def build_trace_artifacts(
    out_dir: Path = ARTIFACTS_DIR,
    work_dir: Path = BUILD_DIR / "trace",
    program: str = DEFAULT_PROGRAM,
) -> TraceArtifact:
    """M2: run ``program`` on the gate netlist and the RTL; verify; write its trace.json.

    Needs netlist.json in ``out_dir`` and the program's listing, hex image and
    golden.json in ``out_dir / program``. Nothing is written unless every
    check passes:

    * the gate level and the RTL agree on every common signal, every cycle
      (every module port among them);
    * no signal is x or z;
    * PC, instruction and register writes match Spike for every instruction;
    * x0 always reads 0;
    * the core halts in the same cycle as Spike.

    Raises:
        PipelineError: a check failed (the message names the cycle and signal).
    """
    netlist_path = out_dir / NETLIST_FILE
    netlist = hardware.load_netlist(netlist_path)
    prog_dir = program_dir(out_dir, program)
    listing = get_program(out_dir, program=program)
    golden = get_golden(out_dir, program=program)
    words = [
        int(line, 16)
        for line in (prog_dir / listing.image_file).read_text().splitlines()
        if not line.startswith("//")
    ]
    work_dir = work_dir / program
    n_sim = min(golden.retired + EXTRA_CYCLES, software.MAX_CYCLES)

    gate = simulate.run_gate_level(netlist_path, words, n_sim, work_dir / "gate")
    rtl = simulate.run_rtl(words, n_sim, work_dir / "rtl")

    # Most specific check first, so a failure names the first cycle and
    # signal that differ: gate vs RTL, then each instruction vs Spike, then
    # the halt.
    names = simulate.compared_signals(gate, rtl, netlist)
    simulate.check_defined(gate, n_sim)
    simulate.check_defined(rtl, n_sim)
    simulate.compare_runs(gate, rtl, names, n_sim)
    writes = simulate.check_against_golden(gate, golden)
    simulate.check_x0(gate, n_sim)
    halt = simulate.halt_cycle(gate, int(listing.tohost, 16))
    if halt != golden.retired - 1:
        raise PipelineError(
            f"the core halts in cycle {halt}, Spike after {golden.retired} instructions"
        )
    n = halt + 1

    trace = _trace_from_run(gate, n, halt, names, writes)
    _write_model(trace, prog_dir / TRACE_FILE)
    return trace


def _hex(value: int | None, width: int) -> str:
    if value is None:
        raise PipelineError("cannot write an x/z value to the trace")
    return f"0x{value:0{(width + 3) // 4}x}"


def _trace_from_run(
    run: simulate.SimRun, n: int, halt: int, compared: list[str], writes: int
) -> TraceArtifact:
    names = sorted(run.cycles[0])
    widths = [run.widths[k] for k in names]
    initial = [_hex(run.cycles[0][k], w) for k, w in zip(names, widths, strict=True)]
    changes: list[list[tuple[int, str]]] = []
    for c in range(1, n):
        prev, cur = run.cycles[c - 1], run.cycles[c]
        changes.append(
            [(i, _hex(cur[k], widths[i])) for i, k in enumerate(names) if cur[k] != prev[k]]
        )
    return TraceArtifact(
        cycles=n,
        halt_cycle=halt,
        signals=[TraceSignal(name=k, width=w) for k, w in zip(names, widths, strict=True)],
        initial=initial,
        changes=changes,
        verification=TraceVerification(
            gate_vs_rtl_signals=len(compared),
            gate_vs_rtl_cycles=n,
            register_writes_checked=writes,
            rtl_simulator="Icarus Verilog",
            gate_simulator="Yosys sim",
        ),
    )


def toolchain_versions() -> dict[str, str]:
    """The exact versions of every tool, as the tools themselves report them."""

    def first_line(*argv: str) -> str:
        out = run_tool(list(argv), check=False)
        return (out.stdout or out.stderr).strip().splitlines()[0]

    spike_help = run_tool([software.SPIKE, "--help"], check=False)
    spike_version = re.search(
        r"Spike RISC-V ISA Simulator (\S+)", spike_help.stderr + spike_help.stdout
    )
    spike_commit = Path("/opt/spike/COMMIT")
    return {
        "python": platform.python_version(),
        "gcc": first_line(software.GCC, "--version"),
        "binutils": first_line(software.OBJDUMP, "--version"),
        "yosys": first_line(hardware.YOSYS, "-V"),
        "iverilog": first_line(simulate.IVERILOG, "-V"),
        "spike": spike_version.group(1) if spike_version else "unknown",
        "spike_commit": spike_commit.read_text().strip() if spike_commit.exists() else "unknown",
    }


def build_all(out_dir: Path = ARTIFACTS_DIR) -> None:
    """Regenerate every artifact (``make artifacts``)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / TOOLCHAIN_FILE).write_text(json.dumps(toolchain_versions(), indent=2) + "\n")
    build_hardware_artifacts(out_dir)
    for c_file in sorted(PROGRAMS_DIR.glob("*.c")):
        build_program_artifacts(c_file, out_dir)
        build_trace_artifacts(out_dir, program=c_file.stem)


# --- serving -------------------------------------------------------------------


def _read[M: BaseModel](model: type[M], name: str, art_dir: Path) -> M:
    path = art_dir / name
    if not path.exists():
        raise ArtifactMissingError(f"{name} has not been generated yet; run 'make artifacts'")
    try:
        return model.model_validate_json(path.read_text())
    except ValidationError as exc:
        raise PipelineError(
            f"{name} is malformed; run 'make artifacts' ({exc.error_count()} errors)"
        ) from exc


def list_programs(art_dir: Path = ARTIFACTS_DIR) -> list[str]:
    """GET /api/programs: the programs that have artifacts, by name."""
    if not art_dir.is_dir():
        return []
    return sorted(d.name for d in art_dir.iterdir() if d.is_dir() and (d / PROGRAM_FILE).exists())


def program_dir(art_dir: Path, program: str) -> Path:
    """The folder holding ``program``'s artifacts.

    Raises:
        KeyError: no program of that name has artifacts.
        ArtifactMissingError: no program has artifacts yet.
    """
    known = list_programs(art_dir)
    if program not in known:
        if not known:
            raise ArtifactMissingError("no program has been built yet; run 'make artifacts'")
        raise KeyError(program)
    return art_dir / program


def get_program(art_dir: Path = ARTIFACTS_DIR, program: str = DEFAULT_PROGRAM) -> ProgramArtifact:
    """GET /api/program: the C source and its asm listing.

    Raises:
        KeyError: no such program.
    """
    return _read(ProgramArtifact, PROGRAM_FILE, program_dir(art_dir, program))


def get_golden(art_dir: Path = ARTIFACTS_DIR, program: str = DEFAULT_PROGRAM) -> GoldenArtifact:
    """GET /api/golden: Spike's commit log.

    Raises:
        KeyError: no such program.
    """
    return _read(GoldenArtifact, GOLDEN_FILE, program_dir(art_dir, program))


def get_trace(art_dir: Path = ARTIFACTS_DIR, program: str = DEFAULT_PROGRAM) -> TraceArtifact:
    """GET /api/trace: every net's value in every cycle.

    Raises:
        KeyError: no such program.
    """
    return _read(TraceArtifact, TRACE_FILE, program_dir(art_dir, program))


def get_gate_counts(art_dir: Path = ARTIFACTS_DIR) -> GateCountReport:
    """GET /api/gate-counts: gate counts per module."""
    return _read(GateCountReport, GATE_COUNTS_FILE, art_dir)


def get_adder_values(art_dir: Path = ARTIFACTS_DIR) -> AdderValuesArtifact:
    """Every net value of the adder for each case (read by the views below)."""
    return _read(AdderValuesArtifact, ADDER_VALUES_FILE, art_dir)


def list_adder_cases(art_dir: Path = ARTIFACTS_DIR) -> list[AdderCaseInfo]:
    """GET /api/adder: the adder cases that have values."""
    values = get_adder_values(art_dir)
    return [AdderCaseInfo(case_id=c.case_id, label=c.label) for c in values.cases]


def get_adder_view(case_id: str, art_dir: Path = ARTIFACTS_DIR) -> AdderView:
    """GET /api/adder/{case_id}: one case's values and its SVG drawing.

    Raises:
        KeyError: no such case.
    """
    values = get_adder_values(art_dir)
    case = next((c for c in values.cases if c.case_id == case_id), None)
    if case is None:
        raise KeyError(case_id)
    netlist_path = art_dir / NETLIST_FILE
    if not netlist_path.exists():
        raise ArtifactMissingError(
            f"{NETLIST_FILE} has not been generated yet; run 'make artifacts'"
        )
    netlist = hardware.load_netlist(netlist_path)
    counts = get_gate_counts(art_dir)
    adder_total = next(m.total_gates for m in counts.modules if m.module == hardware.ADDER_MODULE)
    return AdderView(
        case_id=case.case_id,
        label=case.label,
        a=case.a,
        b=case.b,
        cin=case.cin,
        sum=case.sum,
        cout=case.cout,
        gate_count=adder_total,
        svg=render.adder_svg(netlist, case),
    )


def get_cycle_view(
    n: int, art_dir: Path = ARTIFACTS_DIR, program: str = DEFAULT_PROGRAM
) -> CycleView:
    """GET /api/cycle/{n}: what runs in cycle ``n`` and where line-stepping goes.

    Raises:
        KeyError: no such program, or ``n`` is outside its trace.
    """
    index = views.trace_index(_artifact(TRACE_FILE, program_dir(art_dir, program)))
    listing = get_program(art_dir, program)
    return views.cycle_view(n, listing, get_golden(art_dir, program), index)


def get_module_view(
    path: str, cycle: int, art_dir: Path = ARTIFACTS_DIR, program: str = DEFAULT_PROGRAM
) -> ModuleView:
    """GET /api/view/{path}?cycle=n: one module with every wire's value in that cycle.

    Raises:
        KeyError: no such program or instance path, or ``cycle`` is outside the trace.
    """
    netlist = hardware.load_netlist(_artifact(NETLIST_FILE, art_dir))
    index = views.trace_index(_artifact(TRACE_FILE, program_dir(art_dir, program)))
    return views.module_view(netlist, path, cycle, index, get_gate_counts(art_dir))


def _artifact(name: str, art_dir: Path) -> Path:
    path = art_dir / name
    if not path.exists():
        raise ArtifactMissingError(f"{name} has not been generated yet; run 'make artifacts'")
    return path
