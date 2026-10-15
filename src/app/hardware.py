"""M0 hardware pipeline: synthesis, gate counts and adder evaluation.

Synthesize the core with Yosys, count gates per module, and evaluate the
ALU's adder on the gate netlist with Yosys ``sim``.

Yosys is the only simulator: the values shown on the adder gates come from
``sim`` run on the synthesized netlist, never from Python logic.
"""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.errors import PipelineError
from app.models import (
    AdderCaseValues,
    AdderValuesArtifact,
    Bit,
    GateCountReport,
    ModuleCount,
    SummaryRow,
)
from app.paths import REPO_ROOT, SYNTH_SCRIPT
from app.tools import run_tool
from app.vcd import final_values, read_timeline

YOSYS = "yosys"

# Yosys internal cell type -> gate name. Anything else (besides submodule
# instances) in the netlist is an error.
GATE_TYPES = {
    "$_AND_": "AND",
    "$_OR_": "OR",
    "$_XOR_": "XOR",
    "$_NOT_": "NOT",
    "$_MUX_": "MUX",
    "$_DFF_P_": "DFF",
}
GATE_ORDER = ["AND", "OR", "XOR", "NOT", "MUX", "DFF"]

ADDER_MODULE = "adder32"
FULL_ADDER_MODULE = "full_adder"

SUMMARY_ROWS = [
    ("Top level (register file and RAM as black boxes)", "top"),
    ("Processor (controller + datapath)", "riscvsingle"),
    ("Control unit", "controller"),
    ("Main decoder", "maindec"),
    ("ALU decoder", "aludec"),
    ("Branch unit", "branchunit"),
    ("Datapath", "datapath"),
    ("ALU", "alu"),
    ("ALU adder (ripple-carry)", "adder32"),
    ("Full adder (one bit)", "full_adder"),
    ("ALU logic unit (and/or/xor)", "logicunit"),
    ("ALU shifter", "shifter"),
    ("ALU result mux", "resultmux"),
    ("Immediate decoder", "extend"),
    ("Load/store unit", "lsu"),
]

Netlist = dict[str, Any]


# --- synthesis -----------------------------------------------------------------


def synthesize(out_json: Path) -> Netlist:
    """Run backend/rtl/synth.ys and write the Yosys JSON netlist to ``out_json``."""
    out_json.parent.mkdir(parents=True, exist_ok=True)
    script = SYNTH_SCRIPT.relative_to(REPO_ROOT)
    run_tool(
        [YOSYS, "-q", "-p", f"script {script}; write_json {out_json}"],
        cwd=REPO_ROOT,
        timeout=600,
    )
    return load_netlist(out_json)


def load_netlist(path: Path) -> Netlist:
    """Read a Yosys JSON netlist."""
    with path.open() as f:
        netlist: Netlist = json.load(f)
    return netlist


def is_blackbox(module: dict[str, Any]) -> bool:
    """True if the module was read as a black box (``read_verilog -lib``)."""
    value = module.get("attributes", {}).get("blackbox", 0)
    return bool(int(value, 2)) if isinstance(value, str) else bool(value)


# --- gate counts ---------------------------------------------------------------


def gate_counts(netlist: Netlist) -> GateCountReport:
    """Count gates per module, locally and including submodules.

    Raises:
        PipelineError: a cell is neither an allowed gate nor a known module.
    """
    modules: dict[str, dict[str, Any]] = netlist["modules"]
    local: dict[str, Counter[str]] = {}
    instances: dict[str, Counter[str]] = {}
    for name, mod in modules.items():
        local[name] = Counter()
        instances[name] = Counter()
        for cell_name, cell in mod.get("cells", {}).items():
            ctype = cell["type"]
            if ctype in GATE_TYPES:
                local[name][GATE_TYPES[ctype]] += 1
            elif ctype in modules:
                instances[name][ctype] += 1
            else:
                raise PipelineError(
                    f"cell {cell_name} in module {name} has type {ctype}, "
                    f"outside the gate set {GATE_ORDER}"
                )

    totals: dict[str, Counter[str]] = {}

    def total(name: str) -> Counter[str]:
        if name not in totals:
            acc = Counter(local[name])
            for child, n in instances[name].items():
                for gate, k in total(child).items():
                    acc[gate] += k * n
            totals[name] = acc
        return totals[name]

    def ordered(c: Counter[str]) -> dict[str, int]:
        return {g: c.get(g, 0) for g in GATE_ORDER}

    counts = [
        ModuleCount(
            module=name,
            blackbox=is_blackbox(modules[name]),
            local=ordered(local[name]),
            local_total=sum(local[name].values()),
            total=ordered(total(name)),
            total_gates=sum(total(name).values()),
            instances=dict(sorted(instances[name].items())),
        )
        for name in sorted(modules)
    ]
    by_name = {c.module: c for c in counts}
    missing = [m for _, m in SUMMARY_ROWS if m not in by_name]
    if missing:
        raise PipelineError(f"netlist is missing modules: {', '.join(missing)}")
    return GateCountReport(
        gate_set=GATE_ORDER,
        yosys_version=str(netlist.get("creator", "unknown")),
        summary=[
            SummaryRow(label=label, module=m, total_gates=by_name[m].total_gates)
            for label, m in SUMMARY_ROWS
        ],
        modules=counts,
    )


# --- adder evaluation ----------------------------------------------------------


@dataclass(frozen=True)
class AdderCase:
    """One input case for the M0 adder."""

    case_id: str
    label: str
    a: int
    b: int
    cin: int


def full_adder_order(netlist: Netlist) -> list[str]:
    """Return adder32's full-adder cell names ordered by bit (index 0 = LSB).

    The bit of each cell is read from its connection to adder32's ``a`` port,
    so the order follows the netlist, not the cell names.
    """
    mod = netlist["modules"][ADDER_MODULE]
    a_bits: list[int] = mod["ports"]["a"]["bits"]
    order: dict[int, str] = {}
    for cell_name, cell in mod["cells"].items():
        if cell["type"] != FULL_ADDER_MODULE:
            raise PipelineError(f"{ADDER_MODULE} contains a {cell['type']} cell, not a full adder")
        bit = cell["connections"]["a"][0]
        if bit not in a_bits:
            raise PipelineError(f"{cell_name}.a is not connected to {ADDER_MODULE}.a")
        order[a_bits.index(bit)] = cell_name
    if sorted(order) != list(range(32)):
        raise PipelineError(f"{ADDER_MODULE} does not have one full adder per bit")
    return [order[i] for i in range(32)]


def simulate_adder(
    netlist_path: Path, cases: list[AdderCase], work_dir: Path
) -> AdderValuesArtifact:
    """Evaluate the synthesized adder32 for each case with Yosys ``sim``.

    A small probe module drives adder32's inputs with constants; ``sim``
    evaluates the gate netlist and writes every net to a VCD file.
    """
    netlist = load_netlist(netlist_path)
    fa_cells = full_adder_order(netlist)
    fa_wires = sorted(
        n for n in netlist["modules"][FULL_ADDER_MODULE]["netnames"] if not n.startswith("$")
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for case in cases:
        probe = work_dir / f"probe_{case.case_id}.v"
        vcd = work_dir / f"probe_{case.case_id}.vcd"
        probe.write_text(_probe_verilog(case))
        run_tool(
            [
                YOSYS,
                "-q",
                "-p",
                f"read_json {netlist_path}; read_verilog {probe}; "
                f"hierarchy -top adder_probe; sim -n 1 -vcd {vcd}",
            ],
            cwd=work_dir,
        )
        signals = final_values(read_timeline(vcd.read_text()))
        results.append(_case_values(case, signals, fa_cells, fa_wires))
    return AdderValuesArtifact(module=ADDER_MODULE, cases=results)


def _probe_verilog(case: AdderCase) -> str:
    return (
        "module adder_probe;\n"
        "  wire [31:0] s;\n"
        "  wire cout;\n"
        f"  {ADDER_MODULE} dut (.a(32'h{case.a:08x}), .b(32'h{case.b:08x}), "
        f".cin(1'b{case.cin}), .s(s), .cout(cout));\n"
        "endmodule\n"
    )


def _bit(value: int | None, where: str) -> Bit:
    if value == 0:
        return 0
    if value == 1:
        return 1
    raise PipelineError(f"sim gave no defined 0/1 value for {where}")


def _case_values(
    case: AdderCase,
    signals: dict[str, int | None],
    fa_cells: list[str],
    fa_wires: list[str],
) -> AdderCaseValues:
    def lookup(path: str) -> int | None:
        if path not in signals:
            raise PipelineError(f"sim output has no signal {path}")
        return signals[path]

    bits: list[dict[str, Bit]] = []
    for cell in fa_cells:
        scope = f"adder_probe.dut.{cell.lstrip('\\')}"
        bits.append({w: _bit(lookup(f"{scope}.{w}"), f"{scope}.{w}") for w in fa_wires})

    total = lookup("adder_probe.s")
    cout = _bit(lookup("adder_probe.cout"), "adder_probe.cout")
    if total is None:
        raise PipelineError("sim gave no defined value for adder_probe.s")
    # The per-gate values and the adder outputs come from the same sim run;
    # they must agree or the VCD was read wrongly.
    from_bits = sum(b["s"] << i for i, b in enumerate(bits))
    if from_bits != total or bits[31]["cout"] != cout:
        raise PipelineError("full-adder values disagree with the adder outputs in the VCD")
    return AdderCaseValues(
        case_id=case.case_id,
        label=case.label,
        a=f"0x{case.a:08x}",
        b=f"0x{case.b:08x}",
        cin=_bit(case.cin, "cin"),
        sum=f"0x{total:08x}",
        cout=cout,
        bits=bits,
    )
