// Draws one module view from /api/view. elkjs only places the boxes and
// routes the wires; every value and colour comes from the view itself.
// Layouts are cached per module path, so stepping only redraws values.

const SVG_NS = "http://www.w3.org/2000/svg";
const elk = new globalThis.ELK();
const layouts = new Map(); // path -> { key, graph }

const CHAR_W = 7;
const GATE_SIZE = { AND: [44, 32], OR: [44, 32], XOR: [48, 32], NOT: [36, 26], MUX: [34, 48], DFF: [46, 46] };

function el(name, attrs = {}, text) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (text !== undefined) node.textContent = text;
  return node;
}

function portId(nodeId, port) {
  return `${nodeId}|${port}`;
}

const HEADER = 38; // block name and type sit above the first pin
const PIN_STEP = 18;

function isBox(n) {
  return n.kind === "block" || n.kind === "glue";
}

function nodeSize(n) {
  const ins = n.ports.filter((p) => p.direction === "in").length;
  const outs = n.ports.length - ins;
  if (n.kind === "gate") return GATE_SIZE[n.label] || [44, 32];
  if (n.kind === "port_in" || n.kind === "port_out") return [16 + CHAR_W * n.label.length, 22];
  if (n.kind === "const") return [12 + CHAR_W * n.label.length, 20];
  const longest = Math.max(0, ...n.ports.map((p) => p.name.length));
  const title = Math.max(n.label.length, (n.module || "").length + 12);
  const width = Math.max(130, 2 * CHAR_W * longest + 30, CHAR_W * title + 20);
  return [width, HEADER + PIN_STEP * Math.max(ins, outs, 1)];
}

/** Pin positions: blocks get fixed rows under the header; others let elk place them. */
function portLayout(n, width, p, rowIn, rowOut) {
  const side = p.direction === "in" ? "WEST" : "EAST";
  if (!isBox(n)) return { "elk.port.side": side };
  const row = p.direction === "in" ? rowIn : rowOut;
  return { "elk.port.side": side, x: p.direction === "in" ? -4 : width, y: HEADER + PIN_STEP * row + 4 };
}

function stageIndex(view, n) {
  return view.stages.findIndex((s) => s.id === n.stage);
}

const BAND_HEAD = 46; // room above the drawing for each stage's name and note

/** One shaded, labelled band per stage, spanning the columns elk gave its nodes. */
function drawStages(view, graph, laidNodes) {
  const spans = view.stages.map(() => [Infinity, -Infinity]);
  for (const n of view.nodes) {
    const laid = laidNodes.get(n.id);
    const i = stageIndex(view, n);
    if (!laid || i < 0) continue;
    spans[i][0] = Math.min(spans[i][0], laid.x);
    spans[i][1] = Math.max(spans[i][1], laid.x + laid.width);
  }
  // Bands meet halfway between neighbouring columns, so they tile the width.
  const edges = [-12];
  for (let i = 1; i < spans.length; i += 1) edges.push((spans[i - 1][1] + spans[i][0]) / 2);
  edges.push(graph.width + 12);
  const g = el("g", { class: "stages" });
  view.stages.forEach((s, i) => {
    const x = edges[i];
    const w = edges[i + 1] - x;
    const band = el("g", { class: `stage stage-${i % 2 ? "odd" : "even"}`, "data-stage": s.id });
    band.append(
      el("rect", { class: "stage-band", x, y: -BAND_HEAD, width: w, height: graph.height + BAND_HEAD + 12 }),
      el("text", { class: "stage-name", x: x + 8, y: -BAND_HEAD + 16 }, `${s.id} · ${s.name}`),
      el("text", { class: "stage-note", x: x + 8, y: -BAND_HEAD + 31 }, s.note),
      el("title", {}, `${s.id} (${s.name}): ${s.note}`),
    );
    g.append(band);
  });
  return g;
}

function structureKey(view) {
  return JSON.stringify([view.nodes.map((n) => [n.id, n.ports.length]), view.edges.map((e) => e.id)]);
}

async function layout(view) {
  const key = structureKey(view);
  const cached = layouts.get(view.path);
  if (cached && cached.key === key) return cached.graph;

  const graph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.edgeRouting": "ORTHOGONAL",
      "elk.layered.spacing.nodeNodeBetweenLayers": "70",
      "elk.spacing.nodeNode": "28",
      "elk.layered.spacing.edgeNodeBetweenLayers": "18",
      "elk.spacing.edgeEdge": "8",
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
      "elk.layered.thoroughness": "30",
      "elk.edgeLabels.inline": "false",
      // On the datapath, each stage the backend names is its own column.
      ...(view.stages ? { "elk.partitioning.activate": "true" } : {}),
    },
    children: view.nodes.map((n) => {
      const [width, height] = nodeSize(n);
      let rowIn = 0;
      let rowOut = 0;
      const column = view.stages ? { "elk.partitioning.partition": String(stageIndex(view, n)) } : {};
      return {
        id: n.id,
        width,
        height,
        layoutOptions: { "elk.portConstraints": isBox(n) ? "FIXED_POS" : "FIXED_ORDER", ...column },
        ports: n.ports.map((p) => {
          const opts = portLayout(n, width, p, rowIn, rowOut);
          if (p.direction === "in") rowIn += 1;
          else rowOut += 1;
          const { x, y, ...layoutOptions } = opts;
          const port = { id: portId(n.id, p.name), width: 4, height: 4, layoutOptions };
          return x === undefined ? port : { ...port, x, y };
        }),
      };
    }),
    edges: view.edges.map((e) => ({
      id: e.id,
      sources: [portId(e.source, e.source_port)],
      targets: [portId(e.target, e.target_port)],
      labels: e.width > 1 ? [{ text: e.value, width: CHAR_W * e.value.length, height: 12 }] : [],
    })),
  };
  const result = await elk.layout(graph);
  layouts.set(view.path, { key, graph: result });
  return result;
}

function gateShape(kind, w, h) {
  switch (kind) {
    case "AND":
      return [`M0,0 H${w / 2} A${h / 2},${h / 2} 0 0 1 ${w / 2},${h} H0 Z`];
    case "OR":
      return [`M0,0 Q${w * 0.55},0 ${w},${h / 2} Q${w * 0.55},${h} 0,${h} Q${w * 0.25},${h / 2} 0,0 Z`];
    case "XOR":
      return [
        `M5,0 Q${w * 0.58},0 ${w},${h / 2} Q${w * 0.58},${h} 5,${h} Q${w * 0.3},${h / 2} 5,0 Z`,
        `M0,0 Q${w * 0.22},${h / 2} 0,${h}`,
      ];
    case "NOT":
      return [`M0,0 L${w - 8},${h / 2} L0,${h} Z`, `M${w - 8},${h / 2} a4,4 0 1 0 8,0 a4,4 0 1 0 -8,0`];
    case "MUX":
      return [`M0,0 L${w},${h * 0.22} L${w},${h * 0.78} L0,${h} Z`];
    default:
      return [`M0,0 H${w} V${h} H0 Z`];
  }
}

function drawNode(n, laid, onOpen) {
  const g = el("g", {
    class: `node ${n.kind}${n.drill ? " drillable" : ""}`,
    transform: `translate(${laid.x},${laid.y})`,
    "data-node": n.id,
  });
  const { width: w, height: h } = laid;
  if (n.kind === "gate") {
    for (const d of gateShape(n.label, w, h)) g.append(el("path", { class: "gate-body", d }));
    if (n.label === "MUX" || n.label === "DFF") {
      g.append(el("text", { class: "gate-label", x: w / 2, y: h / 2 + 3 }, n.label));
    }
  } else {
    g.append(el("rect", { class: "box", width: w, height: h, rx: n.kind === "block" || n.kind === "glue" ? 6 : 3 }));
    if (n.kind === "block" || n.kind === "glue") {
      g.append(el("text", { class: "block-name", x: w / 2, y: 15 }, n.label));
      const sub = n.kind === "glue" ? "glue logic" : `${n.module}${n.gate_count ? ` · ${n.gate_count} gates` : ""}`;
      g.append(el("text", { class: "block-type", x: w / 2, y: 28 }, sub));
      g.append(el("line", { class: "header-rule", x1: 0, x2: w, y1: HEADER - 4, y2: HEADER - 4 }));
      if (n.drill) g.append(el("text", { class: "open", x: w - 10, y: 14 }, "⤢"));
    } else {
      g.append(el("text", { class: "port-name", x: w / 2, y: h / 2 + 4 }, n.label));
    }
  }
  // Port names on blocks and on MUX inputs (A = 0, B = 1, S = select).
  const muxNames = { A: "0", B: "1", S: "S" };
  for (const p of laid.ports || []) {
    const name = p.id.slice(n.id.length + 1);
    const isIn = p.x < w / 2;
    if (n.kind === "block" || n.kind === "glue") {
      g.append(el("text", { class: `pin ${isIn ? "in" : "out"}`, x: isIn ? p.x + 7 : p.x - 3, y: p.y + 5 }, name));
    } else if (n.kind === "gate" && n.label === "MUX") {
      g.append(el("text", { class: "pin in", x: p.x + 4, y: p.y + 4 }, muxNames[name] || name));
    }
  }
  const title = n.kind === "block" ? `${n.label} (${n.module})${n.drill ? ": click to open" : ""}` : n.label;
  g.append(el("title", {}, title));
  if (n.drill && n.path) {
    g.setAttribute("role", "button");
    g.setAttribute("tabindex", "0");
    g.addEventListener("click", () => onOpen(n.path));
    g.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        onOpen(n.path);
      }
    });
  }
  return g;
}

function edgeClass(e) {
  const cls = ["wire"];
  if (e.width === 1) cls.push(e.value === "0x1" ? "one" : "zero");
  else cls.push("bus");
  if (e.changed) cls.push("changed");
  if (e.signal === null) cls.push("const");
  return cls.join(" ");
}

/** The register file as a table: every value and mark comes from the view. */
function drawRegisters(container, view) {
  const table = document.createElement("table");
  table.className = "registers";
  table.setAttribute("aria-label", `register file, cycle ${view.cycle}`);
  const head = document.createElement("tr");
  for (const h of ["register", "name", "value", "read by", "stored at the clock edge"]) {
    const th = document.createElement("th");
    th.textContent = h;
    head.append(th);
  }
  table.append(head);
  for (const r of view.registers) {
    const tr = document.createElement("tr");
    tr.dataset.register = String(r.index);
    if (r.read_by.length) tr.classList.add("read");
    if (r.written !== null) tr.classList.add("written");
    const cells = [`x${r.index}`, r.name, r.value, r.read_by.join(", "), r.written ?? ""];
    for (const value of cells) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    }
    table.append(tr);
  }
  const note = document.createElement("p");
  note.className = "registers-note";
  note.textContent =
    "The register file is memory, so it is shown as a table, not as gates. " +
    "Values are the registers' contents during this cycle.";
  container.replaceChildren(note, table);
  container.dataset.path = view.path;
}

/** Draw `view` into `container`. `onOpen(path)` is called when a block is opened. */
export async function drawModule(container, view, onOpen) {
  if (view.kind === "registers") {
    drawRegisters(container, view);
    return;
  }
  if (view.kind === "adder") {
    const doc = new DOMParser().parseFromString(view.svg, "image/svg+xml");
    const opening = container.dataset.path !== view.path;
    container.replaceChildren(document.importNode(doc.documentElement, true));
    if (opening) container.scrollLeft = container.scrollWidth; // bit 0 is on the right
    container.dataset.path = view.path;
    return;
  }
  const graph = await layout(view);
  const laidNodes = new Map(graph.children.map((c) => [c.id, c]));
  const laidEdges = new Map(graph.edges.map((e) => [e.id, e]));
  const pad = 20;
  const top = pad + (view.stages ? BAND_HEAD : 0);
  const svg = el("svg", {
    class: "netview",
    viewBox: `${-pad} ${-top} ${graph.width + 2 * pad} ${graph.height + pad + top}`,
    width: graph.width + 2 * pad,
    height: graph.height + pad + top,
    role: "img",
    "aria-label": `${view.module}, cycle ${view.cycle}`,
  });

  const wires = el("g", { class: "wires" });
  for (const e of view.edges) {
    const laid = laidEdges.get(e.id);
    for (const s of laid?.sections || []) {
      const pts = [s.startPoint, ...(s.bendPoints || []), s.endPoint];
      if (e.changed) {
        // A wide gold line behind the wire: the legend's "changed this cycle".
        wires.append(el("path", { class: "wire-halo", d: "M" + pts.map((p) => `${p.x},${p.y}`).join(" L") }));
      }
      const path = el("path", {
        class: edgeClass(e),
        d: "M" + pts.map((p) => `${p.x},${p.y}`).join(" L"),
        "data-edge": e.id,
        "data-signal": e.signal ?? "",
        "data-value": e.value,
      });
      path.append(el("title", {}, `${e.net} = ${e.value}${e.changed ? " (changed)" : ""}`));
      wires.append(path);
    }
    for (const lab of laid?.labels || []) {
      wires.append(el("text", { class: `wire-value${e.changed ? " changed" : ""}`, x: lab.x, y: lab.y + 10, "data-edge": e.id }, e.value));
    }
  }
  const boxes = el("g", { class: "nodes" });
  for (const n of view.nodes) {
    const laid = laidNodes.get(n.id);
    if (laid) boxes.append(drawNode(n, laid, onOpen));
  }
  if (!view.stages) {
    svg.append(wires, boxes);
    container.replaceChildren(svg);
    container.dataset.path = view.path;
    return;
  }
  svg.append(drawStages(view, graph, laidNodes), wires, boxes);
  const note = document.createElement("p");
  note.className = "stages-note";
  note.textContent =
    "In this single-cycle core all five stages happen within one clock cycle; " +
    "the registers, memory and PC change only at the clock edge that ends it.";
  container.replaceChildren(note, svg);
  container.dataset.path = view.path;
}
