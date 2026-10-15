"""Pipeline entry points.

Building (offline, ``make artifacts``):
    :func:`build_hardware_artifacts`  M0: netlist, gate counts, adder values
    :func:`build_program_artifacts`   M1: program listing, hex image, Spike log

Serving (one function per API endpoint): ``get_*`` read the committed
artifacts and return typed results; nothing is recomputed per request except
the SVG drawing of already-computed values.
"""

import json
import platform
import re
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app import hardware, render, software
from app.errors import ArtifactMissingError, PipelineError
from app.models import (
    AdderCaseInfo,
    AdderValuesArtifact,
    AdderView,
    GateCountReport,
    GoldenArtifact,
    ProgramArtifact,
    SourceLine,
)
from app.paths import ARTIFACTS_DIR, BUILD_DIR, SUM_PROGRAM
from app.tools import run_tool

NETLIST_FILE = "netlist.json"
GATE_COUNTS_FILE = "gate_counts.json"
ADDER_VALUES_FILE = "adder_values.json"
PROGRAM_FILE = "program.json"
GOLDEN_FILE = "golden.json"
TOOLCHAIN_FILE = "toolchain.json"

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

    Raises:
        ProgramRejectedError: the program is outside the subset or does not halt.
    """
    program = software.compile_program(c_file, work_dir)
    asm = software.disassemble(program)
    words = software.memory_image(program, work_dir)
    image_name = f"{c_file.stem}.hex"
    golden = software.run_spike(program)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / image_name).write_text(software.format_hex_image(words))
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
    _write_model(listing, out_dir / PROGRAM_FILE)
    _write_model(golden, out_dir / GOLDEN_FILE)
    return listing, golden


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
        "spike": spike_version.group(1) if spike_version else "unknown",
        "spike_commit": spike_commit.read_text().strip() if spike_commit.exists() else "unknown",
    }


def build_all(out_dir: Path = ARTIFACTS_DIR) -> None:
    """Regenerate every artifact (``make artifacts``)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / TOOLCHAIN_FILE).write_text(json.dumps(toolchain_versions(), indent=2) + "\n")
    build_hardware_artifacts(out_dir)
    build_program_artifacts(out_dir=out_dir)


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


def get_program(art_dir: Path = ARTIFACTS_DIR) -> ProgramArtifact:
    """GET /api/program: the C source and its asm listing."""
    return _read(ProgramArtifact, PROGRAM_FILE, art_dir)


def get_golden(art_dir: Path = ARTIFACTS_DIR) -> GoldenArtifact:
    """GET /api/golden: Spike's commit log."""
    return _read(GoldenArtifact, GOLDEN_FILE, art_dir)


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
