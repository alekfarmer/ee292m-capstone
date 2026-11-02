"""M3: every drawn wire carries the trace's value; cycles map to the right lines.

Values are re-derived here from trace.json (slices included) rather than
trusting views.py.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from app import hardware, pipeline, views
from app.models import ModuleView
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
        "pcadd4": "adder",
        "pcaddbranch": "adder",
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
    assert drill["rf"] is None and drill["lsu"] is None


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
            if view.kind == "adder":
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


def test_the_start_cycle_is_where_the_program_first_loops_back(fresh_dir: Path) -> None:
    """Re-derived from Spike's log: the first backward jump between two C-line cycles."""
    program = pipeline.get_program(fresh_dir)
    golden = pipeline.get_golden(fresh_dir)
    line_of = {line.addr: line.c_line for line in program.asm}
    pcs = [int(e.pc, 16) for e in golden.entries]
    on_c = [line_of[e.pc] is not None for e in golden.entries]
    expected = next(
        n for n in range(1, len(pcs)) if pcs[n] < pcs[n - 1] and on_c[n - 1] and on_c[n]
    )
    assert pipeline.get_start_cycle(fresh_dir).cycle == expected


def test_without_a_loop_the_start_is_the_first_c_line() -> None:
    assert views.start_cycle([0x0, 0x4, 0x8, 0xC], [None, None, 3, 4]).cycle == 2
    assert views.start_cycle([0x0, 0x4], [None, None]).cycle == 0
    assert views.start_cycle([0x0, 0x4, 0x8, 0x4], [None, 3, 3, 3]).cycle == 3
