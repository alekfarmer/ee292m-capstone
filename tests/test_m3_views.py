"""M3: every drawn wire carries the trace's value; cycles map to the right lines.

Values are re-derived here from trace.json (slices included) rather than
trusting views.py.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from app import hardware, pipeline, views
from app.errors import PipelineError
from app.models import ModuleView, StartCycle
from tests.svg_reading import read_sum
from tests.test_m2_trace import decode

Cycle = dict[str, int]


@pytest.fixture(scope="module")
def cycles(fresh_dir: Path) -> list[Cycle]:
    return decode(pipeline.get_trace(fresh_dir))


def all_view_paths(netlist: hardware.Netlist) -> Iterator[str]:
    """Every instance path that has a view (non-black-box modules)."""
    modules = netlist["modules"]

    def walk(module: str, path: str) -> Iterator[str]:
        yield path
        for name, cell in modules[module].get("cells", {}).items():
            ctype = cell["type"]
            if ctype in modules and views.drill_kind(netlist, ctype) is not None:
                yield from walk(ctype, f"{path}.{name.lstrip(chr(92))}")

    yield from walk("top", "top")


@pytest.fixture(scope="module")
def view_paths(fresh_dir: Path) -> list[str]:
    return list(all_view_paths(hardware.load_netlist(fresh_dir / pipeline.NETLIST_FILE)))


def test_the_expected_views_exist(view_paths: list[str]) -> None:
    for path in (
        "top",
        "top.rv",
        "top.rv.dp",
        "top.rv.c",
        "top.rv.c.md",
        "top.rv.dp.alu",
        "top.rv.dp.alu.add",
        "top.rv.dp.pcmux",
        "top.rv.dp.ext",
    ):
        assert path in view_paths, path


def test_datapath_has_the_textbook_blocks(fresh_dir: Path) -> None:
    view = pipeline.get_module_view("top.rv.dp", 0, fresh_dir)
    blocks = {n.id: n.module for n in view.nodes if n.kind == "block"}
    assert blocks == {
        "pcreg": "flopr",
        "pcadd4": "adder32",
        "pcaddbranch": "adder32",
        "pcmux": "mux3",
        "rf": "regfile",
        "ext": "extend",
        "srcamux": "mux3",
        "srcbmux": "mux2",
        "alu": "alu",
        "lsu": "lsu",
        "resultmux": "mux3",
    }
    drill = {n.id: n.drill for n in view.nodes if n.kind == "block"}
    assert drill["alu"] == "blocks" and drill["pcmux"] == "gates"
    assert drill["pcadd4"] == "adder" and drill["lsu"] == "blocks"
    assert drill["rf"] == "registers"


def _check_view(view: ModuleView, cycle: Cycle, prev: Cycle | None) -> None:
    ports = {(n.id, p.name): (p.direction, p.width) for n in view.nodes for p in n.ports}
    coverage: dict[tuple[str, str], int] = {}
    for e in view.edges:
        assert ports[(e.source, e.source_port)][0] == "out", e.id
        direction, width = ports[(e.target, e.target_port)]
        assert direction == "in", e.id
        assert e.target_lo >= 0 and e.target_lo + e.width <= width, e.id
        coverage[(e.target, e.target_port)] = coverage.get((e.target, e.target_port), 0) + e.width
        if e.signal is None:
            continue
        mask = (1 << e.width) - 1
        expected = (cycle[e.signal] >> e.lo) & mask
        assert int(e.value, 16) == expected, f"{view.path} {e.id}: {e.value} != {expected:#x}"
        if prev is not None:
            assert e.changed == (((prev[e.signal] >> e.lo) & mask) != expected), e.id
    # Every input of every block, gate and output port is drawn fully connected.
    for n in view.nodes:
        if n.kind == "glue":
            continue
        for p in n.ports:
            if p.direction == "in":
                assert coverage.get((n.id, p.name)) == p.width, f"{view.path}: {n.id}.{p.name}"


def test_every_wire_of_every_view_carries_the_trace_value(
    fresh_dir: Path, view_paths: list[str], cycles: list[Cycle]
) -> None:
    sample = sorted({0, 1, len(cycles) // 2, len(cycles) - 1})
    for path in view_paths:
        for n in sample:
            view = pipeline.get_module_view(path, n, fresh_dir)
            if view.kind in ("adder", "registers"):
                continue
            _check_view(view, cycles[n], cycles[n - 1] if n > 0 else None)


def test_datapath_wires_match_the_trace_in_every_cycle(
    fresh_dir: Path, cycles: list[Cycle]
) -> None:
    for n in range(len(cycles)):
        view = pipeline.get_module_view("top.rv.dp", n, fresh_dir)
        _check_view(view, cycles[n], cycles[n - 1] if n > 0 else None)


def test_adder_view_shows_this_cycles_operands(fresh_dir: Path, cycles: list[Cycle]) -> None:
    for n in range(len(cycles)):
        view = pipeline.get_module_view("top.rv.dp.alu.add", n, fresh_dir)
        assert view.kind == "adder" and view.svg is not None
        drawn = read_sum(view.svg)
        assert drawn == (cycles[n]["rv.dp.alu.add.s"], cycles[n]["rv.dp.alu.add.cout"]), n


def test_cycle_view_follows_spike_and_the_listing(fresh_dir: Path) -> None:
    program = pipeline.get_program(fresh_dir)
    golden = pipeline.get_golden(fresh_dir)
    lines = []
    for n, entry in enumerate(golden.entries):
        cv = pipeline.get_cycle_view(n, fresh_dir)
        row = program.asm[cv.asm_index]
        assert cv.pc == entry.pc == row.addr
        assert cv.insn == entry.insn == row.hex
        assert cv.c_line == row.c_line
        if entry.rd not in (None, 0):
            assert cv.register_write is not None
            assert (cv.register_write.rd, cv.register_write.value) == (entry.rd, entry.rd_value)
        else:
            assert cv.register_write is None
        lines.append(cv.c_line)
    assert cv.halt


def test_line_stepping_lands_on_the_first_instruction_of_another_line(fresh_dir: Path) -> None:
    golden = pipeline.get_golden(fresh_dir)
    cvs = [pipeline.get_cycle_view(n, fresh_dir) for n in range(len(golden.entries))]
    lines = [c.c_line for c in cvs]
    starts = [n for n in range(len(lines)) if n == 0 or lines[n] != lines[n - 1]]
    for n, cv in enumerate(cvs):
        later = [s for s in starts if s > n]
        assert cv.next_line_cycle == (later[0] if later else None), n
        mine = max(s for s in starts if s <= n)
        earlier = [s for s in starts if s < mine]
        assert cv.prev_line_cycle == (earlier[-1] if earlier else None), n
    # sum.c line 4 (sum += i) runs ten times.
    assert sum(1 for s in starts if lines[s] == 4) == 10


def test_out_of_range_requests_are_key_errors(fresh_dir: Path) -> None:
    with pytest.raises(KeyError):
        pipeline.get_cycle_view(10_000, fresh_dir)
    with pytest.raises(KeyError):
        pipeline.get_module_view("top.nothing", 0, fresh_dir)
    with pytest.raises(KeyError):
        pipeline.get_module_view("top.rv.dp", 10_000, fresh_dir)


# --- where the page opens -------------------------------------------------------


def test_the_page_opens_on_the_first_sum_line(fresh_dir: Path) -> None:
    """For sum.c, the start cycle is the first `sum += i`, where every pane lines up."""
    start = pipeline.get_start_cycle(fresh_dir)
    view = pipeline.get_cycle_view(start.cycle, fresh_dir)
    assert (start.cycle, view.text, view.c_line) == (11, "add a0,a0,a5", 4)
    assert start.reason == "the first time the program loops back"


def test_the_start_cycle_follows_the_loops_back_edge(fresh_dir: Path) -> None:
    """Read off the listing by hand: sum.c's loop closes with its one `bge`.

    The start cycle is the one right after the first time that `bge` is taken,
    and it lands on the loop body's first instruction.
    """
    program = pipeline.get_program(fresh_dir)
    golden = pipeline.get_golden(fresh_dir)
    (bge,) = [line for line in program.asm if line.text.startswith("bge ")]
    assert bge.immediate is not None and bge.immediate < 0  # a branch back
    target = f"0x{int(bge.addr, 16) + bge.immediate:08x}"
    taken = [
        n + 1
        for n, e in enumerate(golden.entries[:-1])
        if e.pc == bge.addr and golden.entries[n + 1].pc == target
    ]
    assert pipeline.get_start_cycle(fresh_dir).cycle == taken[0]


def step(pc: int, line: int | None, jump: bool = False, function: str = "main") -> views.Step:
    """One made-up cycle for the start-cycle rule."""
    return views.Step(pc=pc, c_line=line, function=function, local_jump=jump)


def test_a_branch_back_is_a_loop() -> None:
    run = [step(0x0, None), step(0x4, 3), step(0x8, 3, jump=True), step(0x4, 3)]
    assert views.start_cycle(run) == StartCycle(cycle=3, reason=views.LOOPS_BACK)


def test_calls_and_returns_are_not_loops() -> None:
    # main at 0x10 calls a helper defined above it (0x0), which returns to 0x18.
    helper_first = [
        step(0x10, 5),
        step(0x14, 5),  # jal ra,helper: not a local jump
        step(0x0, 2, function="helper"),
        step(0x4, 2, function="helper"),  # jalr: not a local jump
        step(0x18, 6),
    ]
    assert views.start_cycle(helper_first).reason == views.FIRST_C_LINE
    # main at 0x0 calls a helper defined below it (0x40); its return lands lower.
    helper_after = [
        step(0x0, 5),
        step(0x40, 9, function="helper"),
        step(0x44, 9, function="helper"),
        step(0x4, 6),
    ]
    assert views.start_cycle(helper_after).reason == views.FIRST_C_LINE
    # Even a plain jump back is not a loop if it leaves the function.
    assert views.start_cycle([step(0x40, 9, True, "helper"), step(0x4, 6)]).cycle == 0


def test_a_loop_back_needs_c_lines_on_both_sides() -> None:
    from_startup = [step(0x10, None, jump=True), step(0x0, 3), step(0x4, 3), step(0x8, 3, True)]
    assert views.start_cycle([*from_startup, step(0x4, 3)]).cycle == 4
    into_startup = [step(0x10, 3, jump=True), step(0x0, None), step(0x4, 3, True), step(0x0, 3)]
    assert views.start_cycle(into_startup).cycle == 3


def test_without_a_loop_the_start_is_the_first_c_line() -> None:
    no_loop = [step(0x0, None), step(0x4, None), step(0x8, 3), step(0xC, 4)]
    assert views.start_cycle(no_loop) == StartCycle(cycle=2, reason=views.FIRST_C_LINE)
    no_c = [step(0x0, None), step(0x4, None)]
    assert views.start_cycle(no_c) == StartCycle(cycle=0, reason=views.FIRST_CYCLE)
    assert views.start_cycle([]) == StartCycle(cycle=0, reason=views.FIRST_CYCLE)


def test_a_pc_missing_from_the_listing_is_an_error_not_an_unknown_program(
    fresh_dir: Path,
) -> None:
    program = pipeline.get_program(fresh_dir)
    golden = pipeline.get_golden(fresh_dir)
    stray = golden.entries[3].model_copy(update={"pc": "0x00000000"})
    broken = golden.model_copy(update={"entries": [*golden.entries[:3], stray]})
    with pytest.raises(PipelineError, match="cycle 3: Spike ran pc=0x00000000"):
        views.program_start(program, broken)
