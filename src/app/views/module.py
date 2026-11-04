"""One module of the netlist as a graph, with every wire's value in a cycle.

Blocks, gates and constants become nodes; the wires between them become
edges carrying the trace's value (slices included, so the page never
extracts bits itself). The ALU adder is the textbook drawing instead, and
the register file a table (see :mod:`app.views.registers`).
"""

from dataclasses import dataclass
from typing import Any

from app import hardware, render
from app.errors import PipelineError
from app.models import (
    AdderCaseValues,
    Bit,
    Breadcrumb,
    GateCountReport,
    ModuleView,
    ViewEdge,
    ViewNode,
    ViewPort,
)
from app.views import registers
from app.views.trace import TraceIndex

ROOT = "top"
DEFAULT_VIEW = "top.rv.dp"  # the datapath, as in the textbook

# Modules whose gates are drawn one by one when opened.
GATE_MODULES = {
    "maindec",
    "aludec",
    "branchunit",
    "controller",
    "mux2",
    "mux3",
    "flopr",
    "extend",
    "logicunit",
    "binvert",
    "zerodetect",
}
# A block view with more loose gates than this groups them into one node.
LOOSE_GATES_MAX = 40
GLUE = "logic"

# Port order and direction of each gate cell type.
GATE_PORTS: dict[str, tuple[list[str], list[str]]] = {
    "$_AND_": (["A", "B"], ["Y"]),
    "$_OR_": (["A", "B"], ["Y"]),
    "$_XOR_": (["A", "B"], ["Y"]),
    "$_NOT_": (["A"], ["Y"]),
    "$_MUX_": (["A", "B", "S"], ["Y"]),
    "$_DFF_P_": (["C", "D"], ["Q"]),
}


def resolve(netlist: hardware.Netlist, path: str) -> list[tuple[str, str]]:
    """``[(path, module type), ...]`` from the root down to ``path``.

    Raises:
        KeyError: ``path`` does not name an instance.
    """
    parts = path.split(".")
    if parts[0] != ROOT:
        raise KeyError(path)
    modules = netlist["modules"]
    chain = [(ROOT, ROOT)]
    module = ROOT
    for part in parts[1:]:
        cells = {k.lstrip("\\"): c for k, c in modules[module].get("cells", {}).items()}
        cell = cells.get(part)
        if cell is None or cell["type"] not in modules:
            raise KeyError(path)
        module = cell["type"]
        chain.append((f"{chain[-1][0]}.{part}", module))
    return chain


def drill_kind(netlist: hardware.Netlist, module: str) -> str | None:
    """What opening a block of type ``module`` shows, or None if it cannot be opened.

    Blocks, gates, the adder drawing, or the register table; the RAM is not opened.
    """
    mod = netlist["modules"][module]
    if module == registers.REGFILE_MODULE:
        return "registers"
    if hardware.is_blackbox(mod):
        return None
    if module == hardware.ADDER_MODULE:
        return "adder"
    if module in GATE_MODULES:
        return "gates"
    has_blocks = any(c["type"] in netlist["modules"] for c in mod.get("cells", {}).values())
    return "blocks" if has_blocks else None


@dataclass
class _Port:
    name: str
    direction: str  # "in" | "out"
    bits: list[Any]


@dataclass
class _Node:
    id: str
    kind: str
    label: str
    ports: list[_Port]
    module: str | None = None
    path: str | None = None
    drill: str | None = None
    gate_count: int | None = None


class _NetNames:
    """Find a wire name for a run of bits inside one module."""

    def __init__(self, module: dict[str, Any]) -> None:
        self.nets: dict[str, list[Any]] = {n: v["bits"] for n, v in module["netnames"].items()}
        self.by_bit: dict[int, list[tuple[str, int]]] = {}
        order = sorted(self.nets, key=lambda n: (n.startswith("$"), len(self.nets[n]) == 1, n))
        for name in order:
            for i, b in enumerate(self.nets[name]):
                if isinstance(b, int):
                    self.by_bit.setdefault(b, []).append((name, i))

    def find(self, bits: list[int]) -> tuple[str, int]:
        """``(netname, lowest index)`` of a net holding ``bits`` contiguously, LSB first."""
        for name, i in self.by_bit.get(bits[0], []):
            if self.nets[name][i : i + len(bits)] == bits:
                return name, i
        raise PipelineError(f"no single wire holds bits {bits[:4]}...")

    def display(self, name: str, lo: int, width: int) -> str:
        full = len(self.nets[name])
        shown = name.lstrip("\\")
        if width == full:
            return shown
        if width == 1:
            return f"{shown}[{lo}]"
        return f"{shown}[{lo + width - 1}:{lo}]"


def _gate_node(name: str, cell: dict[str, Any]) -> _Node:
    ins, outs = GATE_PORTS[cell["type"]]
    conns = cell["connections"]
    ports = [_Port(p, "in", conns[p]) for p in ins] + [_Port(p, "out", conns[p]) for p in outs]
    kind = hardware.GATE_TYPES[cell["type"]]
    return _Node(id=name, kind="gate", label=kind, ports=ports, module=kind)


def _build_nodes(
    netlist: hardware.Netlist, module: str, path: str, counts: dict[str, int]
) -> list[_Node]:
    modules = netlist["modules"]
    mod = modules[module]
    cells = mod.get("cells", {})
    pure_gates = all(c["type"] in GATE_PORTS for c in cells.values())
    # In a module made only of gates, every bit is wired separately, so each
    # bit of a bus port gets its own labelled pin (op[0], op[1], ...).
    split = pure_gates and bool(cells)
    nodes: list[_Node] = []
    for name, port in mod["ports"].items():
        bits = port["bits"]
        pieces = (
            [(f"{name}[{i}]", [b]) for i, b in enumerate(bits)]
            if split and len(bits) > 1
            else [(name, bits)]
        )
        for label, piece in pieces:
            if port["direction"] == "input":
                nodes.append(_Node(f"in:{label}", "port_in", label, [_Port("y", "out", piece)]))
            else:
                nodes.append(_Node(f"out:{label}", "port_out", label, [_Port("a", "in", piece)]))

    gates: list[tuple[str, dict[str, Any]]] = []
    for raw_name, cell in mod.get("cells", {}).items():
        name = raw_name.lstrip("\\")
        ctype = cell["type"]
        if ctype in modules:
            sub_ports = modules[ctype]["ports"]
            # An output left unconnected (the PC adders' carry out) has no bits.
            ports = [
                _Port(p, "in" if sub_ports[p]["direction"] == "input" else "out", bits)
                for p, bits in cell["connections"].items()
                if bits
            ]
            child = f"{path}.{name}"
            nodes.append(
                _Node(
                    id=name,
                    kind="block",
                    label=name,
                    ports=ports,
                    module=ctype,
                    path=child,
                    drill=drill_kind(netlist, ctype),
                    gate_count=counts.get(ctype),
                )
            )
        elif ctype in GATE_PORTS:
            gates.append((name, cell))
        else:
            raise PipelineError(f"{path}: cell {name} has unexpected type {ctype}")

    if len(gates) <= LOOSE_GATES_MAX or module in GATE_MODULES:
        nodes.extend(_gate_node(n, c) for n, c in gates)
    elif gates:
        nodes.append(_glue_node(gates, nodes, mod))
    return nodes


def _glue_node(
    gates: list[tuple[str, dict[str, Any]]], others: list[_Node], mod: dict[str, Any]
) -> _Node:
    """Group many loose gates into one node whose ports are the nets crossing it."""
    names = _NetNames(mod)
    gate_nodes = [_gate_node(n, c) for n, c in gates]
    driven = {b for g in gate_nodes for p in g.ports if p.direction == "out" for b in p.bits}
    consumed = {b for g in gate_nodes for p in g.ports if p.direction == "in" for b in p.bits}
    outside_in = {b for n in others for p in n.ports if p.direction == "in" for b in p.bits}
    in_bits = sorted(b for b in consumed - driven if isinstance(b, int))
    out_bits = sorted(b for b in driven & outside_in if isinstance(b, int))

    def group(bits: list[int], direction: str) -> list[_Port]:
        by_net: dict[str, list[tuple[int, int]]] = {}
        for b in bits:
            name, i = names.by_bit[b][0]
            by_net.setdefault(name, []).append((i, b))
        return [
            _Port(name.lstrip("\\"), direction, [b for _, b in sorted(v)])
            for name, v in sorted(by_net.items())
        ]

    ports = group(in_bits, "in") + group(out_bits, "out")
    return _Node(GLUE, "glue", f"{len(gates)} gates", ports, gate_count=len(gates))


def module_view(
    netlist: hardware.Netlist,
    path: str,
    cycle: int,
    index: TraceIndex,
    counts: GateCountReport,
) -> ModuleView:
    """One module, as a graph with each wire's value in ``cycle``.

    Raises:
        KeyError: ``path`` does not name an instance, or ``cycle`` is out of range.
        PipelineError: the netlist and the trace disagree.
    """
    chain = resolve(netlist, path)
    if not 0 <= cycle < len(index.cycles):
        raise KeyError(cycle)
    module = chain[-1][1]
    crumbs = [Breadcrumb(path=p, label=p.rsplit(".", 1)[-1], module=m) for p, m in chain]
    totals = {m.module: m.total_gates for m in counts.modules}
    prefix = "" if path == ROOT else path[len(ROOT) + 1 :] + "."

    if drill_kind(netlist, module) == "adder" and module == hardware.ADDER_MODULE:
        case = adder_case_from_trace(netlist, prefix, cycle, index)
        return ModuleView(
            path=path,
            module=module,
            kind="adder",
            breadcrumbs=crumbs,
            cycle=cycle,
            gate_count=totals.get(module, 0),
            nodes=[],
            edges=[],
            svg=render.adder_svg(netlist, case),
        )

    if module == registers.REGFILE_MODULE:
        return ModuleView(
            path=path,
            module=module,
            kind="registers",
            breadcrumbs=crumbs,
            cycle=cycle,
            gate_count=0,
            nodes=[],
            edges=[],
            svg=None,
            registers=registers.register_rows(prefix, cycle, index),
        )

    nodes = _build_nodes(netlist, module, path, totals)
    edges = _build_edges(netlist["modules"][module], nodes, prefix, cycle, index)
    kind = "gates" if any(n.kind == "gate" for n in nodes) else "blocks"
    return ModuleView(
        path=path,
        module=module,
        kind=kind,
        breadcrumbs=crumbs,
        cycle=cycle,
        gate_count=totals.get(module, 0),
        nodes=[
            ViewNode(
                id=n.id,
                kind=n.kind,
                label=n.label,
                module=n.module,
                path=n.path,
                drill=n.drill,
                gate_count=n.gate_count,
                ports=[
                    ViewPort(name=p.name, direction=p.direction, width=len(p.bits)) for p in n.ports
                ],
            )
            for n in nodes
        ]
        + [
            ViewNode(
                id=c_id,
                kind="const",
                label=label,
                ports=[ViewPort(name="y", direction="out", width=w)],
            )
            for c_id, (label, w) in _consts_seen(edges).items()
        ],
        edges=edges,
        svg=None,
    )


def _consts_seen(edges: list[ViewEdge]) -> dict[str, tuple[str, int]]:
    return {e.source: (e.net, e.width) for e in edges if e.source.startswith("const:")}


def _build_edges(
    mod: dict[str, Any], nodes: list[_Node], prefix: str, cycle: int, index: TraceIndex
) -> list[ViewEdge]:
    names = _NetNames(mod)
    drivers: dict[int, tuple[str, str, int]] = {}
    for node in nodes:
        for port in node.ports:
            if port.direction == "out":
                for pos, b in enumerate(port.bits):
                    if isinstance(b, int):
                        drivers.setdefault(b, (node.id, port.name, pos))

    edges: list[ViewEdge] = []
    for node in nodes:
        for port in node.ports:
            if port.direction != "in":
                continue
            for k0, run in _runs(port.bits, drivers):
                edges.append(_edge(node, port, k0, run, drivers, names, prefix, cycle, index))
    return edges


def _runs(bits: list[Any], drivers: dict[int, tuple[str, str, int]]) -> list[tuple[int, list[Any]]]:
    """Split a sink's bits into runs from one driver port (consecutive) or constants."""
    runs: list[tuple[int, list[Any]]] = []
    for k, b in enumerate(bits):
        if runs:
            _, run = runs[-1]
            last = run[-1]
            if isinstance(b, str) and isinstance(last, str):
                run.append(b)
                continue
            if isinstance(b, int) and isinstance(last, int) and b in drivers and last in drivers:
                (n1, p1, i1), (n2, p2, i2) = drivers[last], drivers[b]
                if (n1, p1) == (n2, p2) and i2 == i1 + 1:
                    run.append(b)
                    continue
        if isinstance(b, int) and b not in drivers:
            raise PipelineError(f"bit {b} has no driver in this module")
        runs.append((k, [b]))
    return runs


def _edge(
    node: _Node,
    port: _Port,
    k0: int,
    run: list[Any],
    drivers: dict[int, tuple[str, str, int]],
    names: _NetNames,
    prefix: str,
    cycle: int,
    index: TraceIndex,
) -> ViewEdge:
    width = len(run)
    edge_id = f"{node.id}.{port.name}.{k0}"
    if isinstance(run[0], str):  # constant bits, LSB first
        if any(b not in ("0", "1") for b in run):
            raise PipelineError(f"{edge_id}: undefined constant bits")
        value = int("".join(reversed(run)), 2)
        label = f"{width}'h{value:x}" if width > 1 else str(value)
        return ViewEdge(
            id=edge_id,
            source=f"const:{edge_id}",
            source_port="y",
            target=node.id,
            target_port=port.name,
            target_lo=k0,
            width=width,
            net=label,
            signal=None,
            lo=0,
            value=_hex(value, width),
            changed=False,
        )

    src_node, src_port, _ = drivers[run[0]]
    net, lo = names.find(run)
    signal = prefix + net.lstrip("\\")
    value = (index.value(cycle, signal) >> lo) & ((1 << width) - 1)
    prev = (index.value(cycle - 1, signal) >> lo) & ((1 << width) - 1) if cycle > 0 else value
    return ViewEdge(
        id=edge_id,
        source=src_node,
        source_port=src_port,
        target=node.id,
        target_port=port.name,
        target_lo=k0,
        width=width,
        net=names.display(net, lo, width),
        signal=signal,
        lo=lo,
        value=_hex(value, width),
        changed=value != prev,
    )


def _hex(value: int, width: int) -> str:
    return f"0x{value:0{(width + 3) // 4}x}"


def _bit(v: int) -> Bit:
    if v not in (0, 1):
        raise PipelineError(f"expected a bit, got {v}")
    return 1 if v else 0


def adder_case_from_trace(
    netlist: hardware.Netlist, prefix: str, cycle: int, index: TraceIndex
) -> AdderCaseValues:
    """The adder's net values in ``cycle``, in the shape the adder drawing takes."""
    fa_cells = hardware.full_adder_order(netlist)
    wires = sorted(
        n
        for n in netlist["modules"][hardware.FULL_ADDER_MODULE]["netnames"]
        if not n.startswith("$")
    )
    bits = [
        {w: _bit(index.value(cycle, f"{prefix}{c.lstrip(chr(92))}.{w}")) for w in wires}
        for c in fa_cells
    ]
    return AdderCaseValues(
        case_id=f"cycle_{cycle}",
        label=f"cycle {cycle}",
        a=f"0x{index.value(cycle, prefix + 'a'):08x}",
        b=f"0x{index.value(cycle, prefix + 'b'):08x}",
        cin=_bit(index.value(cycle, prefix + "cin")),
        sum=f"0x{index.value(cycle, prefix + 's'):08x}",
        cout=_bit(index.value(cycle, prefix + "cout")),
        bits=bits,
    )
