"""Typed shapes of every artifact and API response.

Hex values are strings formatted ``0x%08x`` (uint32) so JSON never carries a
signed or rounded number. Bit order is ``[31:0]``; bit 0 is the LSB.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Hex32 = Annotated[str, StringConstraints(pattern=r"^0x[0-9a-f]{8}$")]
Bit = Literal[0, 1]


class Strict(BaseModel):
    """Base model: unknown fields are an error, instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# --- M1: program.json ------------------------------------------------------


class SourceLine(Strict):
    """One line of the C source."""

    line: int = Field(ge=1)
    text: str


class AsmLine(Strict):
    """One instruction of the linked program, as objdump shows it."""

    addr: Hex32 = Field(description="byte address, 4-aligned")
    hex: Hex32 = Field(description="the 32-bit instruction word")
    text: str = Field(description="objdump text (-M no-aliases), e.g. 'addi a0,zero,0'")
    function: str = Field(description="the enclosing symbol, e.g. 'main' or '_start'")
    c_line: int | None = Field(description="line in the C source, or null (startup code)")


class ProgramArtifact(Strict):
    """The fixed program: C source, asm listing and memory image layout."""

    source_file: str
    c_lines: list[SourceLine]
    asm: list[AsmLine]
    compile_flags: list[str]
    ram_base: Hex32
    ram_size_bytes: int
    entry: Hex32
    tohost: Hex32 = Field(description="store here = halt; value is (exit_code << 1) | 1")
    image_file: str = Field(description="hex image, one little-endian word per line")


# --- M1: golden.json -------------------------------------------------------


class GoldenEntry(Strict):
    """One retired instruction from the Spike commit log."""

    pc: Hex32
    insn: Hex32
    rd: int | None = Field(ge=0, le=31, description="destination register, null if none")
    rd_value: Hex32 | None


class GoldenArtifact(Strict):
    """Spike's commit log for the program, up to and including the halt store."""

    isa: str
    retired: int = Field(description="instructions retired from _start to the halt store")
    max_cycles: int
    exit_code: int
    a0_at_halt: Hex32
    entries: list[GoldenEntry]


# --- M0: gate_counts.json --------------------------------------------------


class ModuleCount(Strict):
    """Gate counts for one module.

    ``local`` counts only cells inside the module; ``total`` also includes
    every submodule instance (recursively). Black boxes count as zero gates.
    """

    module: str
    blackbox: bool
    local: dict[str, int]
    local_total: int
    total: dict[str, int]
    total_gates: int
    instances: dict[str, int] = Field(description="submodule type -> instance count")


class SummaryRow(Strict):
    """One labelled row of the gate-count summary."""

    label: str
    module: str
    total_gates: int


class GateCountReport(Strict):
    """Gate counts per module of the synthesized core."""

    gate_set: list[str]
    yosys_version: str
    summary: list[SummaryRow]
    modules: list[ModuleCount]


# --- M0: adder values and view ----------------------------------------------


class AdderCaseValues(Strict):
    """Every net value inside the synthesized adder32 for one input case.

    ``bits[i]`` maps each wire name of full adder ``i`` (a, b, cin, p, g, t,
    s, cout) to its value, as computed by Yosys ``sim`` on the gate netlist.
    """

    case_id: str
    label: str
    a: Hex32
    b: Hex32
    cin: Bit
    sum: Hex32
    cout: Bit
    bits: list[dict[str, Bit]] = Field(min_length=32, max_length=32)


class AdderValuesArtifact(Strict):
    """adder_values.json: all M0 adder cases."""

    module: str
    cases: list[AdderCaseValues]


class AdderCaseInfo(Strict):
    """A selectable adder case."""

    case_id: str
    label: str


class AdderView(Strict):
    """What the page draws for one case: the values and the rendered SVG."""

    case_id: str
    label: str
    a: Hex32
    b: Hex32
    cin: Bit
    sum: Hex32
    cout: Bit
    gate_count: int
    svg: str


# --- M2: trace.json --------------------------------------------------------


class TraceSignal(Strict):
    """One net of the gate-level design, named relative to ``top``."""

    name: str = Field(description="e.g. 'rv.dp.alu.result' or 'rv.dp.alu.add.g_bit[3].fa.s'")
    width: int = Field(ge=1)


class TraceVerification(Strict):
    """What was checked before the trace was written."""

    gate_vs_rtl_signals: int = Field(description="signals compared with the RTL run each cycle")
    gate_vs_rtl_cycles: int
    register_writes_checked: int = Field(description="register writes matched against Spike")
    rtl_simulator: str
    gate_simulator: str


class TraceArtifact(Strict):
    """Every net's value in every cycle of the gate-level run, as changes.

    ``initial[i]`` is signal ``i`` in cycle 0. ``changes[n - 1]`` lists the
    ``[signal index, value]`` pairs that differ in cycle ``n`` from cycle
    ``n - 1``. Values are hex strings with ``ceil(width / 4)`` digits, bit 0
    the LSB. Cycle ``n`` holds the values just before its rising clock edge,
    so it is instruction ``n`` of golden.json.
    """

    cycles: int
    halt_cycle: int = Field(description="the cycle that stores to tohost")
    signals: list[TraceSignal]
    initial: list[str]
    changes: list[list[tuple[int, str]]]
    verification: TraceVerification


class Health(Strict):
    """Liveness answer."""

    status: Literal["ok"]
