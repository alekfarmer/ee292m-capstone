"""M2: the gate-level run matches Spike and the RTL run, cycle by cycle.

These tests re-derive each check from the artifacts (and, for gate vs RTL,
from fresh simulations) instead of trusting the pipeline's own checks.
"""

import filecmp
from pathlib import Path

import pytest

from app import hardware, pipeline, simulate
from app.models import GoldenArtifact, TraceArtifact
from app.paths import ARTIFACTS_DIR

Cycle = dict[str, int]


def decode(trace: TraceArtifact) -> list[Cycle]:
    """Expand the change list into one full {name: value} dict per cycle."""
    names = [s.name for s in trace.signals]
    cur = {n: int(v, 16) for n, v in zip(names, trace.initial, strict=True)}
    cycles = [dict(cur)]
    for changes in trace.changes:
        for i, v in changes:
            cur[names[i]] = int(v, 16)
        cycles.append(dict(cur))
    return cycles


@pytest.fixture(scope="module")
def trace(fresh_dir: Path) -> TraceArtifact:
    return pipeline.get_trace(fresh_dir)


@pytest.fixture(scope="module")
def cycles(trace: TraceArtifact) -> list[Cycle]:
    return decode(trace)


@pytest.fixture(scope="module")
def golden(fresh_dir: Path) -> GoldenArtifact:
    return pipeline.get_golden(fresh_dir)


def test_one_cycle_per_spike_instruction(
    trace: TraceArtifact, cycles: list[Cycle], golden: GoldenArtifact
) -> None:
    assert trace.cycles == len(cycles) == golden.retired
    assert trace.halt_cycle == golden.retired - 1


def test_pc_and_instruction_match_spike(cycles: list[Cycle], golden: GoldenArtifact) -> None:
    for n, entry in enumerate(golden.entries):
        assert cycles[n]["rv.pc"] == int(entry.pc, 16), f"cycle {n}"
        assert cycles[n]["rv.instr"] == int(entry.insn, 16), f"cycle {n}"


def test_register_writes_match_spike(cycles: list[Cycle], golden: GoldenArtifact) -> None:
    checked = 0
    for n, entry in enumerate(golden.entries):
        c = cycles[n]
        writes = c["rv.dp.rf.we3"] == 1 and c["rv.dp.rf.a3"] != 0
        if entry.rd in (None, 0):
            assert not writes, f"cycle {n}: hardware writes x{c['rv.dp.rf.a3']}, Spike does not"
        else:
            assert writes, f"cycle {n}: Spike writes x{entry.rd}, hardware does not"
            assert c["rv.dp.rf.a3"] == entry.rd, f"cycle {n}"
            assert f"0x{c['rv.dp.rf.wd3']:08x}" == entry.rd_value, f"cycle {n}"
            checked += 1
    assert checked > 20


def test_the_core_halts_with_a0_equal_55(cycles: list[Cycle], fresh_dir: Path) -> None:
    program = pipeline.get_program(fresh_dir)
    last = cycles[-1]
    assert last["mem.dwe"] == 1 and last["mem.daddr"] == int(program.tohost, 16)
    assert last["mem.dwdata"] == (55 << 1) | 1
    a0_writes = [c["rv.dp.rf.wd3"] for c in cycles if c["rv.dp.rf.we3"] and c["rv.dp.rf.a3"] == 10]
    assert a0_writes[-1] == 55


def test_x0_always_reads_zero(cycles: list[Cycle]) -> None:
    for n, c in enumerate(cycles):
        for addr, data in (("a1", "rd1"), ("a2", "rd2")):
            if c[f"rv.dp.rf.{addr}"] == 0:
                assert c[f"rv.dp.rf.{data}"] == 0, f"cycle {n}: x0 read on {data}"


def test_every_net_of_the_netlist_is_traced(trace: TraceArtifact, fresh_dir: Path) -> None:
    netlist = hardware.load_netlist(fresh_dir / pipeline.NETLIST_FILE)
    traced = {s.name for s in trace.signals}
    modules = netlist["modules"]
    missing: list[str] = []

    def walk(module: str, path: str) -> None:
        if hardware.is_blackbox(modules[module]):
            return
        for net in modules[module]["netnames"]:
            name = f"{path}.{net.lstrip(chr(92))}" if path else net.lstrip(chr(92))
            if name not in traced:
                missing.append(name)
        for cell_name, cell in modules[module]["cells"].items():
            if cell["type"] in modules:
                child = cell_name.lstrip(chr(92))
                walk(cell["type"], f"{path}.{child}" if path else child)

    walk("top", "")
    assert not missing, f"{len(missing)} nets not in the trace, e.g. {missing[:5]}"


def test_adder_gates_obey_their_truth_table_every_cycle(cycles: list[Cycle]) -> None:
    for n, c in enumerate(cycles):
        for i in range(32):
            fa = f"rv.dp.alu.add.g_bit[{i}].fa."
            a, b, cin = c[fa + "a"], c[fa + "b"], c[fa + "cin"]
            assert c[fa + "s"] == a ^ b ^ cin, (n, i)
            assert c[fa + "cout"] == (a & b) | (cin & (a ^ b)), (n, i)


def test_gate_level_equals_rtl_every_cycle(
    fresh_dir: Path, golden: GoldenArtifact, tmp_path: Path
) -> None:
    program = pipeline.get_program(fresh_dir)
    words = [
        int(line, 16)
        for line in (fresh_dir / program.image_file).read_text().splitlines()
        if not line.startswith("//")
    ]
    n = golden.retired
    netlist_path = fresh_dir / pipeline.NETLIST_FILE
    gate = simulate.run_gate_level(netlist_path, words, n, tmp_path / "gate")
    rtl = simulate.run_rtl(words, n, tmp_path / "rtl")
    assert len(gate.cycles) == len(rtl.cycles) == n

    ports = set(simulate.port_paths(hardware.load_netlist(netlist_path)))
    common = {k for k in gate.widths if rtl.widths.get(k) == gate.widths[k]}
    assert ports <= common, f"ports missing from a run: {sorted(ports - common)[:5]}"
    for cycle in range(n):
        for name in sorted(common):
            g, r = gate.cycles[cycle][name], rtl.cycles[cycle][name]
            assert g is not None and g == r, f"cycle {cycle}, {name}: gate={g} rtl={r}"


def test_committed_trace_is_up_to_date(fresh_dir: Path) -> None:
    name = pipeline.TRACE_FILE
    assert filecmp.cmp(fresh_dir / name, ARTIFACTS_DIR / name, shallow=False), (
        f"backend/artifacts/{name} is stale; run 'make artifacts'"
    )
