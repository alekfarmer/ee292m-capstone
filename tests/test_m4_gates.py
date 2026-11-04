"""M4: every block opens down to gates, and the spot-check catches wrong bits.

The register table is checked against Spike's own register writes, replayed
here, rather than against the trace the table is built from.
"""

from pathlib import Path

import pytest

from app import hardware, pipeline, spotcheck
from app.models import ModuleView
from tests.test_m2_trace import decode

Cycle = dict[str, int]


@pytest.fixture(scope="module")
def cycles(fresh_dir: Path) -> list[Cycle]:
    return decode(pipeline.get_trace(fresh_dir))


@pytest.fixture(scope="module")
def paths(fresh_dir: Path) -> list[str]:
    return pipeline.list_view_paths(fresh_dir)


# --- every block opens ------------------------------------------------------------------


def test_every_block_but_the_ram_opens(fresh_dir: Path, paths: list[str]) -> None:
    for path in paths:
        view = pipeline.get_module_view(path, 0, fresh_dir)
        for node in view.nodes:
            if node.kind == "block" and node.module != "ram":
                assert node.drill is not None, f"{path}: {node.id} ({node.module}) cannot be opened"


def test_the_former_block_only_modules_reach_gates(fresh_dir: Path, paths: list[str]) -> None:
    """The M3 boxes (shifter, result mux, lsu, PC adders, ALU glue) now open to gates."""
    kinds = {p: pipeline.get_module_view(p, 0, fresh_dir).kind for p in paths}
    for path in (
        "top.rv.dp.alu.sh.lsl.by1",  # one stage of the barrel shifter
        "top.rv.dp.alu.sh.asr.by16",
        "top.rv.dp.alu.rm.m_result",  # the last mux of the result tree
        "top.rv.dp.lsu.st",  # store lanes and byte enables
        "top.rv.dp.lsu.lx",  # load sign extension
        "top.rv.dp.lsu.la.m_by8",
        "top.rv.dp.alu.inv",  # ~b for subtraction
        "top.rv.dp.alu.zd",  # the zero flag
        "top.rv.dp.alu",  # its own few gates are drawn one by one
    ):
        assert kinds.get(path) == "gates", f"{path}: {kinds.get(path)}"
    assert kinds["top.rv.dp.pcadd4"] == kinds["top.rv.dp.pcaddbranch"] == "adder"
    assert kinds["top.rv.dp.rf"] == "registers"


def test_no_view_groups_gates_into_a_glue_box(fresh_dir: Path, paths: list[str]) -> None:
    for path in paths:
        view = pipeline.get_module_view(path, 0, fresh_dir)
        assert not [n for n in view.nodes if n.kind == "glue"], path


# --- the register table ------------------------------------------------------------------


def test_register_table_follows_spikes_writes(fresh_dir: Path) -> None:
    """Replay Spike's writes: at the start of cycle n each register holds its last write."""
    golden = pipeline.get_golden(fresh_dir)
    state = [0] * 32
    for n, entry in enumerate(golden.entries):
        view = pipeline.get_module_view("top.rv.dp.rf", n, fresh_dir)
        assert view.kind == "registers" and view.registers is not None
        shown = [int(r.value, 16) for r in view.registers]
        assert shown == state, f"cycle {n}"
        written = [r for r in view.registers if r.written is not None]
        if entry.rd not in (None, 0):
            assert [(r.index, r.written) for r in written] == [(entry.rd, entry.rd_value)], n
            state[entry.rd] = int(entry.rd_value or "0", 16)
        else:
            assert written == [], n


def test_register_table_marks_the_registers_read(fresh_dir: Path) -> None:
    """add a0,a0,a5 at cycle 11 reads a0 on rd1 and a5 on rd2, and writes a0."""
    view = pipeline.get_module_view("top.rv.dp.rf", 11, fresh_dir)
    rows = {r.name: r for r in view.registers or []}
    assert rows["a0"].read_by == ["rd1"] and rows["a5"].read_by == ["rd2"]
    assert rows["a0"].written is not None
    assert sum(1 for r in rows.values() if r.read_by) == 2


# --- the spot-check itself ---------------------------------------------------------------


def test_the_spot_check_passes_on_fresh_artifacts(fresh_dir: Path, cycles: list[Cycle]) -> None:
    report = spotcheck.check_program("sum", fresh_dir, only_cycles=[0, 11, len(cycles) - 1])
    assert report.problems == []
    assert report.wires > 10_000 and report.gates > 1_000 and report.unit_outputs > 10_000
    # Every unit that has gates of its own is either modelled or a decoder Spike covers.
    assert report.unmodelled <= {"maindec", "aludec", "branchunit", "controller"}


def _view(fresh_dir: Path, path: str, n: int) -> ModuleView:
    return pipeline.get_module_view(path, n, fresh_dir)


def test_a_wrong_wire_value_is_caught(fresh_dir: Path, cycles: list[Cycle]) -> None:
    view = _view(fresh_dir, "top.rv.dp", 11)
    edge = next(e for e in view.edges if e.signal == "rv.dp.pc")
    wrong = edge.model_copy(update={"value": "0x00000000"})
    tampered = view.model_copy(update={"edges": [wrong if e is edge else e for e in view.edges]})
    report = spotcheck.Report("sum")
    spotcheck.check_wires(tampered, cycles, 11, report)
    want = f"the trace has {cycles[11]['rv.dp.pc']:#x}"
    assert len(report.problems) == 1 and want in report.problems[0]


def test_a_gate_that_computes_the_wrong_thing_is_caught(
    fresh_dir: Path, cycles: list[Cycle]
) -> None:
    view = _view(fresh_dir, "top.rv.dp.alu.zd", 11)
    report = spotcheck.Report("sum")
    spotcheck.check_gates(view, cycles, 11, report)
    assert report.problems == []
    gate = next(n for n in view.nodes if n.kind == "gate" and n.label == "OR")
    flipped = [
        e.model_copy(update={"value": "0x0" if e.value == "0x1" else "0x1"})
        if e.source == gate.id
        else e
        for e in view.edges
    ]
    spotcheck.check_gates(view.model_copy(update={"edges": flipped}), cycles, 11, report)
    assert report.problems and f"OR gate {gate.id}" in report.problems[0]


def test_a_wrong_unit_output_is_caught(fresh_dir: Path, cycles: list[Cycle]) -> None:
    """The planted sra-as-srl defect, done to the trace: the shifter model sees it."""
    netlist = hardware.load_netlist(fresh_dir / pipeline.NETLIST_FILE)
    tampered = [dict(c) for c in cycles]
    c = tampered[55]
    assert (c["rv.dp.alu.sh.a"], c["rv.dp.alu.sh.shamt"]) == (0x8000_0020, 16)
    c["rv.dp.alu.sh.y_sra"] = 0x0000_8000
    report = spotcheck.Report("sum")
    spotcheck.check_units(netlist, tampered, report)
    assert report.problems == [
        "cycle 55 rv.dp.alu.sh.y_sra (shifter) is 0x8000, should be 0xffff8000 "
        "from a=0x80000020, shamt=0x10"
    ]


def test_a_wrong_register_table_is_caught(fresh_dir: Path, cycles: list[Cycle]) -> None:
    view = _view(fresh_dir, "top.rv.dp.rf", 11)
    rows = view.registers or []
    swapped = [
        r.model_copy(update={"read_by": ["rd2"] if r.read_by == ["rd1"] else r.read_by})
        for r in rows
    ]
    report = spotcheck.Report("sum")
    spotcheck.check_registers(view.model_copy(update={"registers": swapped}), cycles, 11, report)
    assert any("read_by ['rd2'], but a2=" in p for p in report.problems)


# --- the models, on values worked out by hand ---------------------------------------------


@pytest.mark.parametrize(
    ("module", "inputs", "outputs"),
    [
        ("shifter", {"a": 0x8000_0020, "shamt": 16}, {"y_sra": 0xFFFF_8000, "y_srl": 0x8000}),
        ("shiftright", {"a": 0xF000_0000, "shamt": 4, "fill": 1}, {"y": 0xFF00_0000}),
        ("adder32", {"a": 0xFFFF_FFFF, "b": 1, "cin": 0}, {"s": 0, "cout": 1}),
        ("full_adder", {"a": 1, "b": 1, "cin": 1}, {"s": 1, "cout": 1}),
        ("extend", {"instr": 0xFFF0_0513 >> 7, "immsrc": 0}, {"immext": 0xFFFF_FFFF}),
        ("extend", {"instr": 0xFE00_0EE3 >> 7, "immsrc": 2}, {"immext": 0xFFFF_FFFC}),
        ("extend", {"instr": 0x1234_5537 >> 7, "immsrc": 4}, {"immext": 0x1234_5000}),
        ("loadextend", {"funct3": 0, "aligned": 0x0000_0080}, {"loaddata": 0xFFFF_FF80}),
        ("loadextend", {"funct3": 4, "aligned": 0x0000_0080}, {"loaddata": 0x80}),
        ("storealign", {"size": 0, "offset": 2, "storedata": 0xAB}, {"byteen": 0b0100}),
        (
            "alu",
            {"a": 0xFFFF_FFFF, "b": 1, "alucontrol": 5},  # slt -1, 1
            {"result": 1, "zero": 0, "neg": 1, "ovf": 0, "carry": 1},
        ),
    ],
)
def test_models_on_hand_worked_values(
    module: str, inputs: dict[str, int], outputs: dict[str, int]
) -> None:
    got = spotcheck.MODELS[module](inputs)
    assert {k: got[k] for k in outputs} == outputs
