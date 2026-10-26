"""M0: synthesis keeps hierarchy and the gate set; the drawn adder is correct."""

import filecmp
import itertools
from pathlib import Path

import pytest

from app import hardware, pipeline, render
from app.paths import ARTIFACTS_DIR
from tests.svg_reading import read_sum, wire_values

ALLOWED = set(hardware.GATE_TYPES)


@pytest.fixture(scope="module")
def netlist(fresh_dir: Path) -> hardware.Netlist:
    return hardware.load_netlist(fresh_dir / pipeline.NETLIST_FILE)


def test_netlist_uses_only_the_gate_set(netlist: hardware.Netlist) -> None:
    modules = netlist["modules"]
    for name, mod in modules.items():
        for cell in mod.get("cells", {}).values():
            assert cell["type"] in ALLOWED or cell["type"] in modules, (name, cell["type"])


def test_hierarchy_is_kept_and_memories_are_black_boxes(netlist: hardware.Netlist) -> None:
    modules = netlist["modules"]
    for name in ("top", "riscvsingle", "controller", "maindec", "datapath", "alu", "adder32"):
        assert name in modules, f"module {name} was flattened away"
    assert hardware.is_blackbox(modules["regfile"])
    assert hardware.is_blackbox(modules["ram"])
    assert not modules["regfile"].get("cells")


def test_gate_count_report_lists_the_parts(fresh_dir: Path) -> None:
    report = pipeline.get_gate_counts(fresh_dir)
    rows = {r.module: r.total_gates for r in report.summary}
    for module in ("top", "alu", "maindec", "aludec", "controller"):
        assert rows[module] > 0, module
    assert rows["controller"] >= rows["maindec"] + rows["aludec"]
    assert rows["top"] > rows["alu"] > rows["adder32"]
    assert 500 < rows["top"] < 20_000, "outside the expected 10^3-10^4 range"
    assert report.gate_set == ["AND", "OR", "XOR", "NOT", "MUX", "DFF"]
    top = next(m for m in report.modules if m.module == "top")
    assert top.total["DFF"] == 32, "only the PC is a flip-flop outside the black boxes"


def test_full_adder_keeps_its_textbook_gates(fresh_dir: Path) -> None:
    by_name = {m.module: m for m in pipeline.get_gate_counts(fresh_dir).modules}
    fa = by_name["full_adder"]
    assert fa.local == {"AND": 2, "OR": 1, "XOR": 2, "NOT": 0, "MUX": 0, "DFF": 0}
    assert by_name["adder32"].instances == {"full_adder": 32}
    assert by_name["adder32"].total_gates == 160


@pytest.mark.parametrize(
    ("case_id", "expected_sum", "expected_cout"),
    [("5_plus_3", 0x0000_0008, 0), ("ffffffff_plus_1", 0x0000_0000, 1)],
)
def test_rendered_adder_reads_the_right_sum(
    fresh_dir: Path, case_id: str, expected_sum: int, expected_cout: int
) -> None:
    view = pipeline.get_adder_view(case_id, fresh_dir)
    assert read_sum(view.svg) == (expected_sum, expected_cout)
    assert view.sum == f"0x{expected_sum:08x}"
    assert view.cout == expected_cout


def test_rendered_inputs_match_the_case(fresh_dir: Path) -> None:
    view = pipeline.get_adder_view("5_plus_3", fresh_dir)
    a, b = wire_values(view.svg, "a"), wire_values(view.svg, "b")
    assert sum(v << i for i, v in a.items()) == 5
    assert sum(v << i for i, v in b.items()) == 3


def test_every_full_adder_obeys_its_truth_table(fresh_dir: Path) -> None:
    for case in pipeline.get_adder_values(fresh_dir).cases:
        for i, bit in enumerate(case.bits):
            a, b, cin = bit["a"], bit["b"], bit["cin"]
            assert bit["p"] == a ^ b, (case.case_id, i)
            assert bit["g"] == a & b, (case.case_id, i)
            assert bit["t"] == (a ^ b) & cin, (case.case_id, i)
            assert bit["s"] == a ^ b ^ cin, (case.case_id, i)
            assert bit["cout"] == (a & b) | (cin & (a ^ b)), (case.case_id, i)
            if i < 31:
                assert case.bits[i + 1]["cin"] == bit["cout"], "carry chain is broken"


@pytest.mark.parametrize(
    "name",
    [pipeline.NETLIST_FILE, pipeline.GATE_COUNTS_FILE, pipeline.ADDER_VALUES_FILE],
)
def test_committed_hardware_artifacts_are_up_to_date(fresh_dir: Path, name: str) -> None:
    assert filecmp.cmp(fresh_dir / name, ARTIFACTS_DIR / name, shallow=False), (
        f"backend/artifacts/{name} is stale; run 'make artifacts'"
    )


def test_junctions_mark_branches_not_corners() -> None:
    # One net from (0,0) down to y=10, then left to (-5,10) and right to (5,10).
    branches = [[(0.0, 0.0), (0.0, 10.0), (-5.0, 10.0)], [(0.0, 0.0), (0.0, 10.0), (5.0, 10.0)]]
    assert render.junctions(branches) == [(0.0, 10.0)]
    # A single wire with corners has no junctions.
    assert render.junctions([[(0.0, 0.0), (0.0, 10.0), (5.0, 10.0)]]) == []
    # A T: the second wire leaves the middle of the first wire's segment.
    tee = [[(0.0, 0.0), (10.0, 0.0)], [(5.0, 0.0), (5.0, 5.0)]]
    assert render.junctions(tee) == [(5.0, 0.0)]


def test_every_fanout_net_has_a_junction(fresh_dir: Path) -> None:
    import xml.etree.ElementTree as ET

    svg = pipeline.get_adder_view("5_plus_3", fresh_dir).svg
    dots = {
        (int(el.get("data-bit", "-1")), el.get("data-net"))
        for el in ET.fromstring(svg).iter()
        if el.tag.endswith("circle")
    }
    # a, b, cin and p each feed two gates in every full adder.
    for i in range(32):
        for net in ("a", "b", "cin", "p"):
            assert (i, net) in dots, (i, net)


def test_no_adder_wire_runs_through_a_gate(fresh_dir: Path) -> None:
    """A wire may end at a gate's pins but never cross its body (lrusso3, PR #4)."""
    netlist = hardware.load_netlist(fresh_dir / pipeline.NETLIST_FILE)
    layout = render.tile_layout(netlist)
    half = render.GATE_W / 2
    # The gate body, shrunk by a few pixels so wires ending on its pins don't count.
    boxes = [
        (g.name, g.x - half + 2, g.x + half - 2, g.y + 4, g.y + render.GATE_H - 3)
        for g in layout.gates
    ]
    crossings = []
    for net, paths in render.tile_routes(layout).items():
        for pts in paths:
            for (xa, ya), (xb, yb) in itertools.pairwise(pts):
                for name, x0, x1, y0, y1 in boxes:
                    if (
                        min(xa, xb) <= x1
                        and max(xa, xb) >= x0
                        and min(ya, yb) <= y1
                        and max(ya, yb) >= y0
                    ):
                        crossings.append((layout.net_names[net], name))
    assert not crossings, f"wires through gates: {crossings}"
