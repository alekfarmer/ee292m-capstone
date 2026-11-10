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
        name="registers_drawn_as_zero",
        defect="the page's register table shows every register as 0",
        file="src/web/graph.js",
        old="const cells = [`x${r.index}`, r.name, r.value,",
        new='const cells = [`x${r.index}`, r.name, "0x00000000",',
        caught_at="smoke",
        message="the register table shows other values than the API",
        why=(
            "The backend's table is right, so artifacts, tests and the spot-check "
            "pass; only the smoke check reads the values off the rendered table."
        ),
    ),
    Plant(
        name="lsu_without_a_stage",
        defect="the load/store unit is left out of the datapath's stage table",
        file="src/app/views/module.py",
        old='    "lsu": "MEM",\n',
        new="",
        caught_at="tests",
        message="datapath nodes without a stage: lsu",
        why=(
            "No hardware changes, so artifacts pass; the backend refuses to build a "
            "datapath view with an unlabelled block, and the stage tests name it."
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
        caught_at="artifacts",
        message="Spike writes x12=0xfffffffc, hardware we=1 x12=0x7ffffffc",
        why=(
            "sum.c never runs sra, but tour.c does (-8 >> 1), so Spike sees the wrong "
            "register write while the artifacts are built. Before tour.c (M5) only the "
            "spot-check's shifter model caught this; before M4, nothing did."
        ),
    ),
    Plant(
        name="sltu_decoded_as_slt",
        defect="the ALU decoder sends sltu to the ALU as slt (signed instead of unsigned)",
        file="backend/rtl/aludec.sv",
        old="3'b011:  alucontrol = 4'b0110;",
        new="3'b011:  alucontrol = 4'b0101;",
        caught_at="artifacts",
        message="Spike writes x12=0x00000000, hardware we=1 x12=0x00000001",
        why=(
            "The decoders have no spot-check model, so this was a known blind spot "
            "until M5: sum.c never runs sltu. tour.c runs it on 0xfffffff8 < 65534, "
            "where unsigned (0) and signed (1) differ, so Spike catches it."
        ),
    ),
    Plant(
        name="sh_upper_half_as_lower",
        defect="a halfword store to bytes 2-3 of a word enables bytes 0-1 instead",
        file="backend/rtl/storealign.sv",
        old="2'b01:   byteen = offset[1] ? 4'b1100 : 4'b0011;",
        new="2'b01:   byteen = offset[1] ? 4'b0011 : 4'b0011;",
        caught_at="tests",
        message="rv.dp.lsu.byteen (lsu) is 0x3, should be 0xc",
        why=(
            "No committed program stores a halfword to bytes 2-3, so no wrong value "
            "reaches memory or a register: Spike sees nothing, and gate level and RTL "
            "agree on the wrong design. But the LSU computes byteen every cycle, and "
            "the spot-check's model, from the RV32I specification, disagrees in a "
            "cycle whose inputs look like a halfword at offset 3 (an lhu); make test "
            "runs those models over every cycle of sum.c."
        ),
    ),
    Plant(
        name="sra_wrong_on_small_negatives",
        defect=(
            "the arithmetic right shift fills with 0s when bits 31 and 30 are set and "
            "the shift amount has bits 3 and 0 set (9, 11, 13, 15, 25, ...)"
        ),
        file="backend/rtl/shifter.sv",
        old="shiftright asr (.a(a), .shamt(shamt), .fill(a[31]), .y(y_sra));",
        new=(
            "shiftright asr (.a(a), .shamt(shamt), "
            ".fill(a[31] & ~(a[30] & shamt[3] & shamt[0])), .y(y_sra));"
        ),
        caught_at="spotcheck",
        message="rv.dp.alu.sh.y_sra (shifter) is",
        why=(
            "tour.c's sra and srai shift by 1, 16 and 24 only, so Spike sees nothing, "
            "and gate level and RTL agree on the wrong design. sum.c's operands never "
            "have bits 31 and 30 both set, so the unit-model test over sum.c passes "
            "too. But the shifter computes y_sra every cycle, and in tour.c's "
            "'addi a4,a1,31' it sees a = -3 with 31 on its shift-amount input: only "
            "the spot-check's shifter model, run over every cycle of every program, "
            "sees the wrong value."
        ),
    ),
    Plant(
        name="typed_program_not_opened",
        defect="the page ignores #program= and always opens sum.c",
        file="src/web/app.js",
        old='      hash.get("program") || DEFAULT_PROGRAM,',
        new="      DEFAULT_PROGRAM,",
        caught_at="smoke",
        message="not the program's source",
        why=(
            "The backend builds and serves the typed program correctly, so artifacts, "
            "tests and the spot-check pass; only the smoke check, which builds one "
            "through the API and opens it on the page, sees sum.c instead."
        ),
    ),
    Plant(
        name="explanation_branch_backwards",
        defect="the cycle explanation says a branch is taken when it is not, and the reverse",
        file="src/app/views/explain.py",
        old="taken = c.pcnext != c.pc + 4",
        new="taken = c.pcnext == c.pc + 4",
        caught_at="tests",
        message="FAILED tests/test_explain.py::test_the_numbers_are_the_ones_spike_says",
        why=(
            "The hardware and every drawn value are right, so artifacts pass; the "
            "explanation test works out each branch's outcome from Spike's next pc."
        ),
    ),
    Plant(
        name="explanation_not_drawn",
        defect="the page never fills in the explanation panel",
        file="src/web/app.js",
        old="    renderExplanation(cv.explanation);\n",
        new="",
        caught_at="smoke",
        message="the explanation panel says",
        why=(
            "The API's explanations are right, so artifacts, tests and the spot-check "
            "pass; only the smoke check reads the panel off the rendered page."
        ),
    ),
    Plant(
        name="stepping_scrolls_the_window",
        defect="following the current instruction scrolls the window too (scrollIntoView)",
        file="src/web/app.js",
        old="    if (on) keepInPane(tr);",
        new='    if (on) tr.scrollIntoView({ block: "nearest" });',
        caught_at="smoke",
        message="stepping five cycles scrolled the window",
        why=(
            "Every value on the page is still right; only a browser that scrolls "
            "down, steps and reads the window's position sees it (round 6)."
        ),
    ),
    Plant(
        name="build_and_run_shows_the_old_program",
        defect="after build and run, the page reloads the program it was showing",
        file="src/web/app.js",
        old="    await load(built.program);",
        new="    await load(state.programName);",
        caught_at="smoke",
        message="the typed program to be built and drawn",
        why=(
            "The backend builds the typed program and serves it, so the API checks "
            "pass; only pressing build and run in a browser shows the wrong program."
        ),
    ),
    Plant(
        name="bgeu_as_bge",
        defect="the branch unit decides bgeu as a signed comparison (bge)",
        file="backend/rtl/branchunit.sv",
        old="3'b111:  taken = carry;         // bgeu",
        new="3'b111:  taken = ~(neg ^ ovf);  // bgeu",
        caught_at=None,
        message="",
        why=(
            "A known blind spot: running every instruction is not testing every "
            "case. tour.c's one bgeu compares 65534 with 253, both positive, where "
            "signed and unsigned agree, so Spike sees the same branch; the branch "
            "unit has no spot-check model. A program comparing a negative number "
            "with a positive one, unsigned, would catch it."
        ),
    ),
)
