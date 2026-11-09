"""Each cycle's plain-language explanation quotes the right values and names real wires.

The explanation reads the gate-level trace. This test works its numbers out
another way: it rebuilds the register file from Spike's commit log (every
register write since cycle 0) and decodes the instruction word itself.
"""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from app import pipeline
from app.decode import ABI_NAMES
from app.models import CycleView, GoldenArtifact, ProgramArtifact

PROGRAMS = [c.stem for c in pipeline.committed_sources()]
RAM_BASE, RAM_SIZE = 0x8000_0000, 4096


def shown(value: int) -> str:
    """How a value is written in an explanation: RAM addresses in hex, else signed decimal."""
    value &= 0xFFFF_FFFF
    if RAM_BASE <= value <= RAM_BASE + RAM_SIZE:  # the stack starts at the end
        return f"0x{value:08x}"
    signed = value - (1 << 32) if value >> 31 else value
    return str(signed) if abs(signed) < 10_000 else f"{signed} (0x{value:08x})"


def mention(reg: int, value: int) -> str:
    """How a register and its value are written: 'a5 (= 10)'; x0 is 'zero'."""
    return "zero" if reg == 0 else f"{ABI_NAMES[reg]} (= {shown(value)})"


def registers_before_each_cycle(golden: GoldenArtifact) -> list[list[int]]:
    """The 32 registers at the start of every cycle, from Spike's writes alone."""
    regs = [0] * 32
    out = []
    for e in golden.entries:
        out.append(list(regs))
        if e.rd not in (None, 0) and e.rd_value is not None:
            regs[e.rd] = int(e.rd_value, 16)
    return out


def sext(value: int, bits: int) -> int:
    return value - (1 << bits) if value >> (bits - 1) & 1 else value


def i_imm(w: int) -> int:
    return sext(w >> 20, 12)


def s_imm(w: int) -> int:
    return sext(((w >> 25) << 5) | ((w >> 7) & 31), 12)


class Run:
    """One program's cycles, its listing, and what Spike says about each."""

    def __init__(self, art: Path, program: str) -> None:
        self.listing: ProgramArtifact = pipeline.get_program(art, program)
        self.golden: GoldenArtifact = pipeline.get_golden(art, program)
        self.regs = registers_before_each_cycle(self.golden)
        self.views: list[CycleView] = [
            pipeline.get_cycle_view(n, art, program) for n in range(self.golden.retired)
        ]


@pytest.fixture(scope="module")
def runs(fresh_dir: Path) -> dict[str, Run]:
    return {p: Run(fresh_dir, p) for p in PROGRAMS}


@pytest.fixture(scope="module")
def datapath(fresh_dir: Path) -> tuple[set[str], set[str]]:
    """The datapath's block ids and the trace signals its wires carry."""
    view = pipeline.get_module_view("top.rv.dp", 0, fresh_dir, program="sum")
    blocks = {n.id for n in view.nodes if n.kind == "block"}
    return blocks, {e.signal for e in view.edges if e.signal}


def every_cycle(runs: dict[str, Run]) -> Iterator[tuple[str, int, Run, CycleView]]:
    """Every cycle of every program, with its run and cycle view."""
    for program, run in runs.items():
        for n, cv in enumerate(run.views):
            yield program, n, run, cv


def test_every_cycle_is_explained_in_three_parts(runs: dict[str, Run]) -> None:
    for program, n, _, cv in every_cycle(runs):
        e = cv.explanation
        where = f"{program} cycle {n}"
        assert e.what.startswith(f"`{cv.text}`"), where
        assert e.look_for and e.context, where
        for part in (e.what, e.look_for, e.deeper or ""):  # context quotes real C, braces and all
            assert "None" not in part and "{" not in part, f"{where}: {part}"


def test_the_numbers_are_the_ones_spike_says(runs: dict[str, Run]) -> None:
    for program, n, run, cv in every_cycle(runs):
        e, entry = cv.explanation, run.golden.entries[n]
        w, regs = int(entry.insn, 16), run.regs[n]
        rd, rs1, rs2 = (w >> 7) & 31, (w >> 15) & 31, (w >> 20) & 31
        pc = int(entry.pc, 16)
        result = int(entry.rd_value, 16) if entry.rd_value is not None else None
        nxt = int(run.golden.entries[n + 1].pc, 16) if n + 1 < len(run.golden.entries) else None
        mnemonic = cv.text.split()[0]
        where = f"{program} cycle {n} ({cv.text}): {e.what}"
        if e.kind == "halt":
            a0 = int(run.golden.a0_at_halt, 16)
            assert f"a0 = {shown(a0)}" in e.what, where
        elif e.kind == "alu":
            assert mention(rs1, regs[rs1]) in e.what, where
            assert mention(rs2, regs[rs2]) in e.what, where
            if rd != 0:
                assert result is not None and shown(result) in e.what, where
        elif e.kind == "alu_imm":
            assert rs1 == 0 or mention(rs1, regs[rs1]) in e.what, where
            if rd != 0:
                assert result is not None and shown(result) in e.what, where
        elif e.kind == "load":
            address = (regs[rs1] + i_imm(w)) & 0xFFFF_FFFF
            assert shown(address) in e.what and result is not None, where
            assert shown(result) in e.what, where
        elif e.kind == "store":
            address = (regs[rs1] + s_imm(w)) & 0xFFFF_FFFF
            assert shown(address) in e.what and mention(rs2, regs[rs2]) in e.what, where
        elif e.kind == "branch":
            assert mention(rs1, regs[rs1]) in e.what and mention(rs2, regs[rs2]) in e.what, where
            taken = nxt != pc + 4
            assert ("is taken" if taken else "is not taken") in e.what, where
            assert nxt is not None and shown(nxt) in e.what, where
        elif e.kind in ("call", "jump", "return"):
            assert nxt is not None and shown(nxt) in e.what, where
            if e.kind == "call":
                assert shown(pc + 4) in e.what, where
        elif e.kind == "upper":
            assert result is not None and shown(result) in e.what, where
        else:
            pytest.fail(f"{where}: unknown kind {e.kind}")
        assert e.kind in KINDS[mnemonic], where


# Which kinds of explanation each instruction may get.
KINDS = {
    **{m: {"alu"} for m in ("add", "sub", "and", "or", "xor", "sll", "srl", "sra", "slt", "sltu")},
    **{
        m: {"alu_imm"}
        for m in ("addi", "andi", "ori", "xori", "slli", "srli", "srai", "slti", "sltiu")
    },
    **{m: {"load"} for m in ("lb", "lh", "lw", "lbu", "lhu")},
    **{m: {"store", "halt"} for m in ("sb", "sh", "sw")},
    **{m: {"branch"} for m in ("beq", "bne", "blt", "bge", "bltu", "bgeu")},
    "jal": {"call", "jump"},
    "jalr": {"return", "jump", "call"},
    "lui": {"upper"},
    "auipc": {"upper"},
}


def test_every_kind_of_explanation_is_used(runs: dict[str, Run]) -> None:
    used = {cv.explanation.kind for _, _, _, cv in every_cycle(runs)}
    expected = {"alu", "alu_imm", "load", "store", "branch", "call", "jump", "return"}
    assert expected | {"upper", "halt"} <= used


def test_what_to_look_for_names_real_blocks_and_wires(
    runs: dict[str, Run], datapath: tuple[set[str], set[str]]
) -> None:
    blocks, signals = datapath
    for program, n, _, cv in every_cycle(runs):
        e = cv.explanation
        where = f"{program} cycle {n} ({cv.text})"
        assert e.blocks and e.wires, where
        for b in e.blocks:
            assert b in blocks, f"{where}: no block '{b}' on the datapath"
            assert f"({b})" in e.look_for, f"{where}: '{b}' not named in: {e.look_for}"
        for s in e.wires:
            assert s in signals, f"{where}: no wire carries '{s}' on the datapath"
            assert s.removeprefix("rv.dp.") in e.look_for, f"{where}: {s} not in: {e.look_for}"


def test_going_deeper_opens_a_view_that_exists(runs: dict[str, Run], fresh_dir: Path) -> None:
    paths = set(pipeline.list_view_paths(fresh_dir))
    for program, n, _, cv in every_cycle(runs):
        e = cv.explanation
        assert (e.deeper is None) == (e.deeper_view is None), f"{program} cycle {n}"
        assert e.deeper_view is None or e.deeper_view in paths, f"{program} cycle {n}"


def test_the_c_line_is_quoted(runs: dict[str, Run]) -> None:
    for program, n, run, cv in every_cycle(runs):
        context = cv.explanation.context
        if cv.c_line is None:
            assert "line" not in context.split(":")[0], f"{program} cycle {n}: {context}"
        else:
            code = run.listing.c_lines[cv.c_line - 1].text.strip()
            assert f"line {cv.c_line}" in context and code in context, f"{program} {n}"


def test_sum_cycle_11_reads_as_the_loop_body(runs: dict[str, Run]) -> None:
    """The opening screen of sum.c, worked out by hand: sum (a0) = 0, i (a5) = 1."""
    e = runs["sum"].views[11].explanation
    assert e.what == "`add a0,a0,a5` adds a0 (= 0) and a5 (= 1) and saves the result, 1, in a0."
    assert e.context == "In the C program this is line 4: sum += i;"


CLAIM = re.compile(r"\b(regwrite|alusrc|pcsrc) is (\d+)")


def expected_controls(mnemonic: str, pc: int, nxt: int | None) -> dict[str, int]:
    """What the control unit must set for an instruction, from the RV32I specification."""
    branch, store = mnemonic in KINDS and "branch" in KINDS[mnemonic], mnemonic in STORES
    controls = {"regwrite": 0 if branch or store else 1}
    if mnemonic in KINDS and "alu_imm" in KINDS[mnemonic]:
        controls["alusrc"] = 1
    if branch:
        controls["pcsrc"] = int(nxt != pc + 4)
    elif mnemonic == "jal":
        controls["pcsrc"] = 1
    elif mnemonic == "jalr":
        controls["pcsrc"] = 2
    return controls


STORES = {"sb", "sh", "sw"}


def test_every_control_value_named_is_the_right_one(runs: dict[str, Run]) -> None:
    """'alusrc is 1', 'pcsrc is 2', 'regwrite is 0': each claim matches the instruction."""
    claims = 0
    for program, n, run, cv in every_cycle(runs):
        pc = int(run.golden.entries[n].pc, 16)
        nxt = int(run.golden.entries[n + 1].pc, 16) if n + 1 < run.golden.retired else None
        expected = expected_controls(cv.text.split()[0], pc, nxt)
        for name, value in CLAIM.findall(cv.explanation.look_for):
            claims += 1
            assert name in expected, f"{program} cycle {n}: unexpected claim about {name}"
            assert int(value) == expected[name], (
                f"{program} cycle {n} ({cv.text}): says {name} is {value}, "
                f"should be {expected[name]}"
            )
    assert claims > 100
