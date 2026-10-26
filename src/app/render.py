"""Draw the synthesized ripple-carry adder as plain SVG with net values.

The drawing is built from the netlist: the gates in each tile are the cells
of the ``full_adder`` module, wired as the netlist connects them, and the
tiles are ordered by their connection to adder32's ``a`` port. Each wire
element carries ``data-bit``, ``data-net`` and ``data-value``, and a class
``v0`` or ``v1``; the values come from Yosys ``sim`` (see hardware.py).

Layout of one tile (inputs on top, sum at the bottom, carry right to left):

    a  b
    gates at level 0       <- cin enters from the right
    gates at level 1
    gates at level 2       -> cout leaves on the left
    s
"""

import itertools
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from app.errors import PipelineError
from app.hardware import FULL_ADDER_MODULE, GATE_TYPES, Netlist, full_adder_order
from app.models import AdderCaseValues

TILE_W = 150
ROW_Y0 = 70  # top of the first gate row
ROW_DY = 95
GATE_W = 36
GATE_H = 30
MARGIN_X = 64
MARGIN_TOP = 34
CARRY_IN_PORT = "cin"
CARRY_OUT_PORT = "cout"


@dataclass(frozen=True)
class Gate:
    """A placed gate cell of the full adder."""

    name: str
    kind: str  # AND, OR, XOR, NOT, MUX
    inputs: dict[str, int]  # port -> net bit
    output: int
    level: int
    x: float
    y: float

    def input_point(self, port: str) -> tuple[float, float]:
        """Where the wire for input ``port`` meets the gate (top edge)."""
        ports = sorted(self.inputs)
        if len(ports) == 1:
            return (self.x, self.y)
        step = (GATE_W - 12) / (len(ports) - 1)
        return (self.x - (GATE_W - 12) / 2 + step * ports.index(port), self.y + 2)

    def output_point(self) -> tuple[float, float]:
        """Where the output wire leaves the gate (bottom tip)."""
        return (self.x, self.y + GATE_H)


@dataclass(frozen=True)
class TileLayout:
    """Gate placement and pin positions shared by all 32 tiles."""

    gates: list[Gate]
    net_names: dict[int, str]  # bit -> wire name
    in_ports: dict[str, int]  # port name -> bit
    out_ports: dict[str, int]
    height: float
    cin_y: float
    cout_y: float


def _cell_src_line(cell: dict[str, Any]) -> tuple[int, str]:
    src = str(cell.get("attributes", {}).get("src", ""))
    try:
        return (int(src.rsplit(":", 1)[1].split(".", 1)[0]), src)
    except IndexError, ValueError:
        return (0, src)


def tile_layout(netlist: Netlist) -> TileLayout:
    """Place the full adder's gates in rows by logic level (from its netlist)."""
    mod = netlist["modules"][FULL_ADDER_MODULE]
    in_ports: dict[str, int] = {}
    out_ports: dict[str, int] = {}
    for name, port in mod["ports"].items():
        if len(port["bits"]) != 1:
            raise PipelineError(f"{FULL_ADDER_MODULE}.{name} is not one bit wide")
        (in_ports if port["direction"] == "input" else out_ports)[name] = port["bits"][0]

    net_names: dict[int, str] = {}
    for name, net in sorted(mod["netnames"].items(), key=lambda kv: kv[0].startswith("$")):
        for bit in net["bits"]:
            if isinstance(bit, int):
                net_names.setdefault(bit, name)

    cells = sorted(mod["cells"].items(), key=lambda kv: _cell_src_line(kv[1]))
    driver_cell: dict[int, str] = {}
    raw: dict[str, tuple[str, dict[str, int], int]] = {}
    for name, cell in cells:
        kind = GATE_TYPES.get(cell["type"])
        if kind is None or kind == "DFF":
            raise PipelineError(f"unexpected cell {cell['type']} in {FULL_ADDER_MODULE}")
        conns = {p: bits[0] for p, bits in cell["connections"].items()}
        dirs = cell["port_directions"]
        outs = [p for p in conns if dirs[p] == "output"]
        if len(outs) != 1:
            raise PipelineError(f"gate {name} does not have exactly one output")
        out = conns[outs[0]]
        raw[name] = (kind, {p: b for p, b in conns.items() if dirs[p] == "input"}, out)
        driver_cell[out] = name

    levels: dict[str, int] = {}

    def level(name: str, seen: frozenset[str] = frozenset()) -> int:
        if name in seen:
            raise PipelineError(f"combinational loop through {name}")
        if name not in levels:
            ins = raw[name][1].values()
            levels[name] = 1 + max(
                (level(driver_cell[b], seen | {name}) for b in ins if b in driver_cell),
                default=-1,
            )
        return levels[name]

    rows: dict[int, list[str]] = {}
    for name, _ in cells:
        rows.setdefault(level(name), []).append(name)

    gates: list[Gate] = []
    for lvl, names in sorted(rows.items()):
        for j, name in enumerate(names):
            kind, ins, out = raw[name]
            x = TILE_W * (j + 1) / (len(names) + 1)
            gates.append(Gate(name, kind, ins, out, lvl, x, ROW_Y0 + lvl * ROW_DY))
    n_rows = max(rows) + 1
    return TileLayout(
        gates=gates,
        net_names=net_names,
        in_ports=in_ports,
        out_ports=out_ports,
        height=ROW_Y0 + n_rows * ROW_DY + 30,
        cin_y=ROW_Y0 + ROW_DY - 30,
        cout_y=ROW_Y0 + (n_rows - 1) * ROW_DY + GATE_H + 22,
    )


def _gate_shape(g: Gate) -> str:
    """SVG for a gate pointing down, centred on (g.x, g.y)."""
    x, y, w, h = g.x, g.y, GATE_W / 2, GATE_H
    if g.kind == "AND":
        d = f"M{x - w},{y} H{x + w} V{y + h - w} A{w},{w} 0 0 1 {x - w},{y + h - w} Z"
        extra = ""
    elif g.kind in ("OR", "XOR"):
        d = (
            f"M{x - w},{y} Q{x},{y + 8} {x + w},{y} "
            f"Q{x + w - 2},{y + h * 0.65} {x},{y + h} Q{x - w + 2},{y + h * 0.65} {x - w},{y} Z"
        )
        extra = (
            f'<path class="gate-line" d="M{x - w},{y - 5} Q{x},{y + 3} {x + w},{y - 5}"/>'
            if g.kind == "XOR"
            else ""
        )
    else:  # NOT, MUX: a labelled box
        d = f"M{x - w},{y} H{x + w} V{y + h} H{x - w} Z"
        extra = ""
    label = f'<text class="gate-label" x="{x}" y="{y + 15}">{g.kind}</text>'
    return (
        f'<g class="gate" data-gate={quoteattr(g.name)} data-kind="{g.kind}">'
        f'<path class="gate-body" d="{d}"/>{extra}{label}</g>'
    )


Point = tuple[float, float]
JOG_STEP = 9


def _path_d(pts: list[Point]) -> str:
    return "M" + " L".join(f"{x:g},{y:g}" for x, y in pts)


def _direction(a: Point, b: Point) -> tuple[int, int]:
    return ((b[0] > a[0]) - (b[0] < a[0]), (b[1] > a[1]) - (b[1] < a[1]))


def junctions(paths: list[list[Point]]) -> list[Point]:
    """Points where one net's wires branch (three or more directions meet).

    A vertex in the middle of another wire's straight segment counts that
    segment's two directions, so a T-junction is found as well as a corner
    shared by diverging wires.
    """
    segments = [(a, b) for pts in paths for a, b in itertools.pairwise(pts) if a != b]
    found: list[Point] = []
    for pt in {p for pts in paths for p in pts}:
        dirs: set[tuple[int, int]] = set()
        for a, b in segments:
            if pt == a:
                dirs.add(_direction(a, b))
            elif pt == b:
                dirs.add(_direction(b, a))
            elif _on_segment(pt, a, b):
                dirs.add(_direction(pt, a))
                dirs.add(_direction(pt, b))
        if len(dirs) >= 3:
            found.append(pt)
    return sorted(found)


def _on_segment(p: Point, a: Point, b: Point) -> bool:
    if a[0] == b[0] == p[0]:
        return min(a[1], b[1]) < p[1] < max(a[1], b[1])
    if a[1] == b[1] == p[1]:
        return min(a[0], b[0]) < p[0] < max(a[0], b[0])
    return False


def _wire(path: str, bit: int, net: str, value: int, cls: str = "wire") -> str:
    title = f"bit {bit}: {net} = {value}"
    return (
        f'<path class="{cls} v{value}" d="{path}" data-bit="{bit}" '
        f'data-net={quoteattr(net)} data-value="{value}"><title>{escape(title)}</title></path>'
    )


def adder_svg(netlist: Netlist, case: AdderCaseValues) -> str:
    """Render all 32 full adders of adder32 with the values of ``case``."""
    full_adder_order(netlist)  # validates that the netlist is a 32-bit ripple chain
    layout = tile_layout(netlist)
    width = MARGIN_X * 2 + 32 * TILE_W
    height = MARGIN_TOP + layout.height + 40
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" class="adder" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" '
        f'aria-label="32-bit ripple-carry adder, {escape(case.label)}">'
    ]
    for i in range(32):
        tx = MARGIN_X + (31 - i) * TILE_W  # bit 31 on the left, bit 0 on the right
        parts.append(_tile(layout, case.bits[i], i, tx))
    # Carry between tiles: cout of bit i rises into cin of bit i+1 at their boundary.
    for i in range(31):
        bx = MARGIN_X + (31 - i) * TILE_W
        v = case.bits[i]["cout"]
        parts.append(
            _wire(
                f"M{bx},{MARGIN_TOP + layout.cout_y} V{MARGIN_TOP + layout.cin_y}",
                i,
                "cout",
                v,
                "wire carry",
            )
        )
    right = MARGIN_X + 32 * TILE_W
    parts.append(
        f'<text class="port-label" x="{right + 4}" y="{MARGIN_TOP + layout.cin_y - 6}">'
        f"cin={case.cin}</text>"
        f'<text class="port-label end" x="{MARGIN_X - 4}" y="{MARGIN_TOP + layout.cout_y - 6}">'
        f"cout={case.cout}</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


SIDE_CHANNEL = 12  # distance of the detour channel from the tile edge


def _crosses_gate(pts: list[Point], gates: list[Gate]) -> bool:
    """True if any segment enters a gate's body (ending on its pins is fine)."""
    half = GATE_W / 2
    for (xa, ya), (xb, yb) in itertools.pairwise(pts):
        for g in gates:
            x0, x1, y0, y1 = g.x - half + 2, g.x + half - 2, g.y + 4, g.y + GATE_H - 3
            if min(xa, xb) <= x1 and max(xa, xb) >= x0 and min(ya, yb) <= y1 and max(ya, yb) >= y0:
                return True
    return False


def tile_sources(layout: TileLayout) -> dict[int, Point]:
    """Where each net starts inside a tile: a top pin, the carry-in edge or a gate output."""
    sources: dict[int, Point] = {}
    top_inputs = [p for p in sorted(layout.in_ports) if p != CARRY_IN_PORT]
    for k, port in enumerate(top_inputs):
        sources[layout.in_ports[port]] = (TILE_W * (k + 1) / (len(top_inputs) + 1), 0.0)
    if CARRY_IN_PORT in layout.in_ports:
        sources[layout.in_ports[CARRY_IN_PORT]] = (float(TILE_W), layout.cin_y)
    for g in layout.gates:
        sources[g.output] = g.output_point()
    return sources


def tile_routes(layout: TileLayout) -> dict[int, list[list[Point]]]:
    """Every wire of a tile as an axis-aligned polyline, grouped by net."""
    sources = tile_sources(layout)
    routes: dict[int, list[list[Point]]] = {}

    # Wires into gate inputs, with a separate jog height per net to limit overlap.
    jog: dict[int, int] = {}
    for g in layout.gates:
        for port, net_bit in sorted(g.inputs.items()):
            if net_bit not in sources:
                raise PipelineError(f"net {net_bit} of the full adder has no driver")
            (x1, y1), (x2, y2) = sources[net_bit], g.input_point(port)
            k = jog.setdefault(net_bit, len(jog))
            if y1 == y2 or x1 == x2:
                pts = [(x1, y1), (x2, y2)]
            elif x1 >= TILE_W:  # carry in from the right edge
                pts = [(x1, y1), (x2, y1), (x2, y2)]
            else:
                ym = y2 - 10 - JOG_STEP * (k % 4)
                pts = [(x1, y1), (x1, ym), (x2, ym), (x2, y2)]
                if _crosses_gate(pts, layout.gates):
                    # Skips a row (g -> OR): go round the gates in a side channel.
                    xc = TILE_W - SIDE_CHANNEL if x1 > TILE_W / 2 else SIDE_CHANNEL
                    yd = y1 + 8
                    pts = [(x1, y1), (x1, yd), (xc, yd), (xc, ym), (x2, ym), (x2, y2)]
                    if _crosses_gate(pts, layout.gates):
                        raise PipelineError(f"no gate-free route for net {net_bit}")
            routes.setdefault(net_bit, []).append(pts)

    # Output wires.
    for port, net_bit in sorted(layout.out_ports.items()):
        (x1, y1) = sources[net_bit]
        if port == CARRY_OUT_PORT:
            pts = [(x1, y1), (x1, layout.cout_y), (0.0, layout.cout_y)]
        else:
            pts = [(x1, y1), (x1, layout.height - 6)]
        routes.setdefault(net_bit, []).append(pts)
    return routes


def _tile(layout: TileLayout, values: Mapping[str, int], bit: int, tx: float) -> str:
    oy = MARGIN_TOP
    parts = [f'<g class="tile" data-bit="{bit}" transform="translate({tx},{oy})">']
    parts.append(
        f'<rect class="tile-frame" x="2" y="-30" width="{TILE_W - 4}" '
        f'height="{layout.height + 26}" rx="6"/>'
    )
    parts.append(f'<text class="bit-label" x="{TILE_W / 2}" y="-14">bit {bit}</text>')

    def value_of(net_bit: int) -> tuple[str, int]:
        name = layout.net_names[net_bit]
        if name not in values:
            raise PipelineError(f"no value for wire {name} of full adder {bit}")
        return name, values[name]

    top_inputs = [p for p in sorted(layout.in_ports) if p != CARRY_IN_PORT]
    sources = tile_sources(layout)
    for port in top_inputs:
        x, _ = sources[layout.in_ports[port]]
        _, v = value_of(layout.in_ports[port])
        parts.append(f'<text class="pin-label" x="{x}" y="-2">{escape(port)}={v}</text>')
    routes = tile_routes(layout)
    for port, net_bit in sorted(layout.out_ports.items()):
        if port != CARRY_OUT_PORT:
            x1, _ = sources[net_bit]
            _, v = value_of(net_bit)
            parts.append(
                f'<text class="pin-label out" x="{x1}" y="{layout.height + 8}" '
                f'data-bit="{bit}" data-net={quoteattr(port)}>{escape(port)}{bit}={v}</text>'
            )

    for net_bit, paths in routes.items():
        name, v = value_of(net_bit)
        for pts in paths:
            parts.append(_wire(_path_d(pts), bit, name, v))
        for jx, jy in junctions(paths):
            parts.append(
                f'<circle class="junction v{v}" cx="{jx}" cy="{jy}" r="3.2" '
                f'data-bit="{bit}" data-net={quoteattr(name)}/>'
            )

    # Labels for internal nets, next to the gate that drives them.
    for g in layout.gates:
        if g.output not in layout.out_ports.values():
            name = layout.net_names[g.output]
            ox, oy2 = g.output_point()
            parts.append(
                f'<text class="net-label" x="{ox + 5}" y="{oy2 + 10}">{escape(name)}</text>'
            )
    parts.extend(_gate_shape(g) for g in layout.gates)
    parts.append("</g>")
    return "".join(parts)
