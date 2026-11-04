"""What the panes show per cycle, and the cycle the page opens on."""

from dataclasses import dataclass

from app.decode import ABI_NAMES
from app.errors import PipelineError
from app.models import (
    AsmLine,
    CycleView,
    GoldenArtifact,
    ProgramArtifact,
    RegisterWrite,
    StartCycle,
)
from app.views.trace import TraceIndex


def _line_runs(c_lines: list[int | None]) -> list[tuple[int, int]]:
    """Maximal runs ``(start, end_exclusive)`` of cycles on the same C line."""
    runs: list[tuple[int, int]] = []
    start = 0
    for n in range(1, len(c_lines) + 1):
        if n == len(c_lines) or c_lines[n] != c_lines[start]:
            runs.append((start, n))
            start = n
    return runs


LOOPS_BACK = "the first time the program loops back"
FIRST_C_LINE = "the first cycle that runs a line of C"
FIRST_CYCLE = "the first cycle"


@dataclass(frozen=True)
class Step:
    """One cycle of a run, as the start-cycle rule sees it.

    ``local_jump`` is true for an instruction that can close a loop: a
    conditional branch, or a ``jal`` that saves no return address. Calls
    (``jal ra``) and returns (``jalr``) are not loops.
    """

    pc: int
    c_line: int | None
    function: str
    local_jump: bool


def can_close_a_loop(line: AsmLine) -> bool:
    """Whether ``line`` is a branch or a plain jump (not a call or a return)."""
    return line.format == "B" or line.text.startswith("jal zero,")


def start_cycle(run: list[Step]) -> StartCycle:
    """The cycle the page opens on, for any program.

    Start-up code (no C line) is a poor first screen, so the page opens where
    the program first loops back: the cycle after a branch or plain jump to a
    lower address in the same function, both cycles on C lines. Calls and
    returns do not count. For ``sum.c`` (and any loop GCC rotates, test at the
    bottom) that is the first pass through the loop body; for a loop with its
    test at the top it is the second test. Without a loop, it opens on the
    first cycle on a C line, and failing that on cycle 0.
    """
    for n in range(1, len(run)):
        jump, there = run[n - 1], run[n]
        if (
            jump.local_jump
            and there.pc < jump.pc
            and there.function == jump.function
            and jump.c_line is not None
            and there.c_line is not None
        ):
            return StartCycle(cycle=n, reason=LOOPS_BACK)
    first = next((n for n, step in enumerate(run) if step.c_line is not None), None)
    if first is not None:
        return StartCycle(cycle=first, reason=FIRST_C_LINE)
    return StartCycle(cycle=0, reason=FIRST_CYCLE)


def program_start(program: ProgramArtifact, golden: GoldenArtifact) -> StartCycle:
    """The start cycle of one program run (see :func:`start_cycle`).

    Raises:
        PipelineError: Spike ran a pc that is not in the program's listing.
    """
    line_at = {line.addr: line for line in program.asm}
    run = []
    for n, entry in enumerate(golden.entries):
        line = line_at.get(entry.pc)
        if line is None:
            raise PipelineError(f"cycle {n}: Spike ran pc={entry.pc}, which is not in the listing")
        step = Step(int(entry.pc, 16), line.c_line, line.function, can_close_a_loop(line))
        run.append(step)
    return start_cycle(run)


def cycle_view(
    n: int, program: ProgramArtifact, golden: GoldenArtifact, index: TraceIndex
) -> CycleView:
    """Everything the panes need about cycle ``n``."""
    if not 0 <= n < len(golden.entries):
        raise KeyError(n)
    by_addr = {line.addr: i for i, line in enumerate(program.asm)}
    asm_rows = [by_addr[e.pc] for e in golden.entries]
    c_lines = [program.asm[i].c_line for i in asm_rows]
    runs = _line_runs(c_lines)
    run = next(k for k, (s, e) in enumerate(runs) if s <= n < e)

    entry = golden.entries[n]
    write = None
    if entry.rd not in (None, 0) and entry.rd_value is not None:
        write = RegisterWrite(rd=entry.rd, name=ABI_NAMES[entry.rd], value=entry.rd_value)
    prev_snap = index.cycles[n - 1] if n > 0 else index.cycles[n]
    changed = sum(1 for k, v in index.cycles[n].items() if prev_snap.get(k) != v)
    line = program.asm[asm_rows[n]]
    return CycleView(
        cycle=n,
        cycles=len(golden.entries),
        pc=entry.pc,
        insn=entry.insn,
        asm_index=asm_rows[n],
        text=line.text,
        c_line=line.c_line,
        register_write=write,
        changed_signals=changed if n > 0 else 0,
        prev_line_cycle=runs[run - 1][0] if run > 0 else None,
        next_line_cycle=runs[run + 1][0] if run + 1 < len(runs) else None,
        halt=n == len(golden.entries) - 1,
    )
