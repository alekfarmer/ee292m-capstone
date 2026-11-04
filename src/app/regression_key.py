"""The answer key for ``make regression``: planted defects, and what must catch each.

Each plant is one small text edit to a copy of the repository. ``make
regression`` applies it and runs the copy through the same stages a developer
would after an edit (``make artifacts``, then ``make test``, then ``make
spot-check``, then the smoke check against a server started from the copy).
The plant behaves as the key says when the first stage to fail is
``caught_at`` and its output contains ``message``.

A plant with ``caught_at=None`` is a known blind spot: every stage must pass,
and the regenerated artifacts must differ from the committed ones, which
shows the edit reached the design rather than doing nothing.

Because artifacts are regenerated first, the "committed artifact is up to
date" tests compare the copy with itself here. They catch an edit made
without ``make artifacts``; this harness asks the harder question of what
catches a defect once the artifacts are rebuilt from it.
"""

from dataclasses import dataclass
from typing import Literal

Stage = Literal["artifacts", "tests", "spotcheck", "smoke"]
STAGES: tuple[Stage, ...] = ("artifacts", "tests", "spotcheck", "smoke")


@dataclass(frozen=True)
class Plant:
    """One planted defect and the answer: which stage catches it, and why."""

    name: str
    defect: str
    file: str  # relative to the repository root
    old: str  # must occur exactly once in ``file``
    new: str
    caught_at: Stage | None
    message: str  # expected in the failing stage's output ("" for a blind spot)
    why: str


PLANTS: tuple[Plant, ...] = (
    Plant(
        name="bge_as_blt",
        defect="the RTL branch unit takes bge when blt would be taken",
        file="backend/rtl/branchunit.sv",
        old="3'b101:  taken = ~(neg ^ ovf);  // bge",
        new="3'b101:  taken = neg ^ ovf;     // bge",
        caught_at="artifacts",
        message="cycle 11: hardware is at pc=0x8000004c",
        why=(
            "Gate level and RTL run the same wrong design, so they agree; only the "
            "comparison with Spike sees the loop exit before its first pass (bge 10, 1 "
            "falls through, so the body never runs)."
        ),
    ),
    Plant(
        name="adder_xor_as_or_in_gates",
        defect="the gate netlist's full adders use OR where the RTL says XOR",
        file="backend/rtl/synth.ys",
        old="abc -g AND,OR,XOR,MUX * full_adder %d\n",
        new="abc -g AND,OR,XOR,MUX * full_adder %d\nchtype -set $_OR_ full_adder/t:$_XOR_\n",
        caught_at="artifacts",
        message="gate level and RTL differ",
        why=(
            "The RTL is still right, so the gate-vs-RTL comparison, which runs first, "
            "names the first cycle and wire where the gates go wrong."
        ),
    ),
    Plant(
        name="wires_drawn_as_zero",
        defect="the page draws every wire in a module view as 0",
        file="src/web/graph.js",
        old="for (const e of view.edges) {",
        new='for (const e of view.edges.map((w) => ({ ...w, value: "0x0" }))) {',
        caught_at="smoke",
        message="the drawn pc wire does not show 0x80000000",
        why=(
            "Every backend number is still right, so artifacts and tests pass; only "
            "the smoke check reads the values off the rendered page."
        ),
    ),
    Plant(
        name="start_one_cycle_late",
        defect="the backend opens the page one cycle after the loop closes",
        file="src/app/views/cycle.py",
        old="return StartCycle(cycle=n, reason=LOOPS_BACK)",
        new="return StartCycle(cycle=n + 1, reason=LOOPS_BACK)",
        caught_at="tests",
        message="FAILED tests/test_m3_views.py::test_the_page_opens_on_the_first_sum_line",
        why=(
            "No hardware changes, so artifacts pass; the views tests pin sum.c's start "
            "to cycle 11, the first add a0,a0,a5."
        ),
    ),
    Plant(
        name="sra_as_srl",
        defect="the shifter's arithmetic right shift fills with 0s instead of the sign bit",
        file="backend/rtl/shifter.sv",
        old="shiftright asr (.a(a), .shamt(shamt), .fill(a[31]), .y(y_sra));",
        new="shiftright asr (.a(a), .shamt(shamt), .fill(1'b0), .y(y_sra));",
        caught_at="spotcheck",
        message="cycle 55 rv.dp.alu.sh.y_sra (shifter) is 0x8000, should be 0xffff8000",
        why=(
            "sum.c never runs an sra instruction, so Spike, which compares only pc, "
            "instruction and register writes, sees nothing, and gate level and RTL agree "
            "on the wrong design. But the shifter computes y_sra every cycle, and the "
            "spot-check's model of the shifter says 0x80000020 >> 16 is 0xffff8000. "
            "(A blind spot until M4.)"
        ),
    ),
    Plant(
        name="sltu_decoded_as_slt",
        defect="the ALU decoder sends sltu to the ALU as slt (signed instead of unsigned)",
        file="backend/rtl/aludec.sv",
        old="3'b011:  alucontrol = 4'b0110;",
        new="3'b011:  alucontrol = 4'b0101;",
        caught_at=None,
        message="",
        why=(
            "A known blind spot. sum.c never runs sltu or sltiu, so Spike sees nothing, "
            "and gate level and RTL agree on the wrong design. The spot-check models "
            "the datapath units, not the decoders: the ALU does exactly what the wrong "
            "alucontrol asks. Programs that run every instruction come with M5."
        ),
    ),
)
