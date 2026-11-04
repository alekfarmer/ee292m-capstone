// The page: C, assembly, machine code and hardware panes, and a stepper.
// It computes nothing. Every value (PC, fields, wire values, which cycle
// "next C line" goes to) comes from the backend API.

import { drawModule } from "./graph.js";

const DEFAULT_VIEW = "top.rv.dp"; // the datapath
const DEFAULT_PROGRAM = "sum";

const $ = (id) => document.getElementById(id);
const els = {
  cLines: $("c-lines"),
  cFile: $("c-file"),
  asm: $("asm"),
  insnSummary: $("insn-summary"),
  fields: $("fields"),
  effect: $("effect"),
  crumbs: $("crumbs"),
  viewInfo: $("view-info"),
  view: $("view"),
  error: $("error"),
  slider: $("cycle"),
  cycleLabel: $("cycle-label"),
  startReason: $("start-reason"),
  play: $("play"),
  speed: $("speed"),
  fit: $("fit"),
};

const state = {
  programName: DEFAULT_PROGRAM, // which program's artifacts to show
  program: null,
  cycles: 0,
  cycle: 0,
  cv: null, // the current /api/cycle response
  viewPath: DEFAULT_VIEW,
  selectedLine: null, // C line selected by clicking (highlights its asm)
  timer: null,
  request: 0, // newest request number; older responses are dropped
};

function programQuery() {
  return `program=${encodeURIComponent(state.programName)}`;
}

async function getJson(path) {
  const resp = await fetch(path);
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(body.detail || `request failed: ${resp.status}`);
  return body;
}

function showError(message) {
  // Clear the drawing so a stale result never sits beside an error.
  els.view.replaceChildren();
  els.error.textContent = message;
  els.error.hidden = false;
  stopPlay();
}

function clearError() {
  els.error.hidden = true;
  els.error.textContent = "";
}

function text(tag, value, cls) {
  const node = document.createElement(tag);
  node.textContent = value;
  if (cls) node.className = cls;
  return node;
}

// --- static panes ---------------------------------------------------------------

function renderSource(program) {
  els.cFile.textContent = program.source_file;
  els.cLines.replaceChildren(
    ...program.c_lines.map((l) => {
      const li = text("li", l.text || " ");
      li.dataset.line = String(l.line);
      li.tabIndex = 0;
      li.addEventListener("click", () => selectLine(l.line));
      return li;
    }),
  );
  const head = document.createElement("tr");
  for (const h of ["", "address", "hex", "instruction", "line"]) head.append(text("th", h));
  const rows = program.asm.map((a, i) => {
    const tr = document.createElement("tr");
    tr.dataset.index = String(i);
    if (a.c_line !== null) tr.dataset.line = String(a.c_line);
    tr.append(
      text("td", "", "marker"),
      text("td", a.addr.slice(2), "addr"),
      text("td", a.hex.slice(2), "hex"),
      text("td", a.text, "insn"),
      text("td", a.c_line === null ? "–" : String(a.c_line), "cl"),
    );
    tr.addEventListener("click", () => selectLine(a.c_line));
    return tr;
  });
  els.asm.replaceChildren(head, ...rows);
}

function selectLine(line) {
  state.selectedLine = state.selectedLine === line ? null : line;
  for (const node of document.querySelectorAll("[data-line]")) {
    node.classList.toggle("selected", state.selectedLine !== null && node.dataset.line === String(state.selectedLine));
  }
}

// --- per-cycle panes ------------------------------------------------------------

function renderCycle(cv) {
  els.slider.value = String(cv.cycle);
  els.cycleLabel.textContent = `cycle ${cv.cycle} / ${cv.cycles - 1}${cv.halt ? " · halt" : ""}`;
  for (const li of els.cLines.children) {
    li.classList.toggle("current", cv.c_line !== null && li.dataset.line === String(cv.c_line));
  }
  for (const tr of els.asm.querySelectorAll("tr[data-index]")) {
    const on = tr.dataset.index === String(cv.asm_index);
    tr.classList.toggle("current", on);
    tr.querySelector(".marker").textContent = on ? "▶" : "";
    if (on) tr.scrollIntoView({ block: "nearest" });
  }

  const line = state.program.asm[cv.asm_index];
  els.insnSummary.replaceChildren(
    text("code", line.text),
    text("span", `  ${line.format ?? "?"}-type · ${line.opcode_name}`),
    ...(line.immediate !== null ? [text("span", ` · immediate ${line.immediate}`)] : []),
  );
  els.fields.replaceChildren(
    ...line.fields.map((f) => {
      const box = document.createElement("div");
      box.className = `field f-${f.name.replace(/[^a-z0-9]/gi, "").slice(0, 6)}`;
      box.style.flexGrow = String(f.hi - f.lo + 1);
      box.append(
        text("div", `${f.name} [${f.hi === f.lo ? f.hi : `${f.hi}:${f.lo}`}]`, "fname"),
        text("div", f.bits, "fbits"),
        text("div", f.meaning, "fmeaning"),
      );
      return box;
    }),
  );
  const parts = [];
  if (cv.register_write) parts.push(`writes ${cv.register_write.name} (x${cv.register_write.rd}) ← ${cv.register_write.value}`);
  else parts.push("writes no register");
  parts.push(`${cv.changed_signals} nets changed since the previous cycle`);
  if (cv.halt) parts.push("halt: stores to tohost");
  els.effect.textContent = parts.join(" · ");

  $("prev").disabled = cv.cycle === 0;
  $("first").disabled = cv.cycle === 0;
  $("next").disabled = cv.cycle === cv.cycles - 1;
  $("last").disabled = cv.cycle === cv.cycles - 1;
  $("prev-line").disabled = cv.prev_line_cycle === null;
  $("next-line").disabled = cv.next_line_cycle === null;
}

function renderCrumbs(view) {
  const items = view.breadcrumbs.map((b, i) => {
    const last = i === view.breadcrumbs.length - 1;
    const label = `${b.label} (${b.module})`;
    if (last) return text("span", label, "crumb current");
    const btn = text("button", label, "crumb");
    btn.type = "button";
    btn.addEventListener("click", () => openView(b.path));
    return btn;
  });
  els.crumbs.replaceChildren(...items.flatMap((x, i) => (i ? [text("span", " › ", "sep"), x] : [x])));
  const kinds = {
    adder: "gate level, textbook layout",
    gates: "gate level",
    blocks: "blocks",
    registers: "memory: 32 registers",
  };
  const what = kinds[view.kind] ?? view.kind;
  els.viewInfo.textContent = view.kind === "registers" ? what : `${what} · ${view.gate_count} gates`;
}

// --- loading ----------------------------------------------------------------------

async function show(cycle, path = state.viewPath) {
  const ticket = ++state.request;
  try {
    const [cv, view] = await Promise.all([
      getJson(`/api/cycle/${cycle}?${programQuery()}`),
      getJson(`/api/view/${encodeURIComponent(path)}?cycle=${cycle}&${programQuery()}`),
    ]);
    if (ticket !== state.request) return; // a newer step superseded this one
    state.cycle = cycle;
    state.cv = cv;
    state.viewPath = path;
    history.replaceState(null, "", `#program=${state.programName}&cycle=${cycle}&view=${path}`);
    clearError();
    renderCycle(cv);
    renderCrumbs(view);
    await drawModule(els.view, view, openView);
  } catch (err) {
    if (ticket === state.request) showError(err.message);
  }
}

function openView(path) {
  show(state.cycle, path);
}

function step(target) {
  if (target === null || target === undefined) return;
  const n = Math.max(0, Math.min(state.cycles - 1, target));
  if (n !== state.cycle || !state.cv) show(n);
}

// --- playing ----------------------------------------------------------------------

function stopPlay() {
  if (state.timer !== null) clearInterval(state.timer);
  state.timer = null;
  els.play.textContent = "▶ play";
  els.play.setAttribute("aria-pressed", "false");
}

function togglePlay() {
  if (state.timer !== null) return stopPlay();
  if (state.cycle >= state.cycles - 1) step(0);
  els.play.textContent = "⏸ pause";
  els.play.setAttribute("aria-pressed", "true");
  state.timer = setInterval(() => {
    if (state.cycle >= state.cycles - 1) return stopPlay();
    step(state.cycle + 1);
  }, Number(els.speed.value));
}

function wireControls() {
  $("first").addEventListener("click", () => step(0));
  $("last").addEventListener("click", () => step(state.cycles - 1));
  $("prev").addEventListener("click", () => step(state.cycle - 1));
  $("next").addEventListener("click", () => step(state.cycle + 1));
  $("prev-line").addEventListener("click", () => step(state.cv?.prev_line_cycle));
  $("next-line").addEventListener("click", () => step(state.cv?.next_line_cycle));
  els.play.addEventListener("click", togglePlay);
  els.speed.addEventListener("change", () => {
    if (state.timer !== null) {
      stopPlay();
      togglePlay();
    }
  });
  els.slider.addEventListener("input", () => step(Number(els.slider.value)));
  els.fit.addEventListener("change", () => els.view.classList.toggle("fit", els.fit.checked));
  const changed = $("show-changed");
  changed.addEventListener("change", () => els.view.classList.toggle("no-changes", !changed.checked));
  document.addEventListener("keydown", (ev) => {
    if (ev.target instanceof HTMLInputElement || ev.target instanceof HTMLSelectElement) return;
    const keys = {
      ArrowLeft: () => step(state.cycle - 1),
      ArrowRight: () => step(state.cycle + 1),
      ArrowUp: () => step(state.cv?.prev_line_cycle),
      ArrowDown: () => step(state.cv?.next_line_cycle),
      Home: () => step(0),
      End: () => step(state.cycles - 1),
      " ": togglePlay,
    };
    if (keys[ev.key]) {
      ev.preventDefault();
      keys[ev.key]();
    }
  });
}

async function init() {
  wireControls();
  try {
    // The URL can name a program, a cycle and a view:
    //   #program=sum&cycle=11&view=top.rv.dp.alu
    const hash = new URLSearchParams(location.hash.slice(1));
    state.programName = hash.get("program") || DEFAULT_PROGRAM;
    state.program = await getJson(`/api/program?${programQuery()}`);
    const golden = await getJson(`/api/golden?${programQuery()}`);
    state.cycles = golden.retired;
    els.slider.max = String(state.cycles - 1);
    renderSource(state.program);
    // Without a cycle in the URL, open where the backend says the layers line up.
    const opening = await getJson(`/api/start?${programQuery()}`);
    const asked = Number(hash.get("cycle") ?? "x");
    const linked = Number.isInteger(asked);
    const start = linked ? Math.min(Math.max(asked, 0), state.cycles - 1) : opening.cycle;
    // Say why only when the page chose the cycle; a link chose it otherwise.
    els.startReason.textContent = linked ? "" : `It opened on cycle ${opening.cycle}, ${opening.reason}.`;
    await show(start, hash.get("view") || DEFAULT_VIEW);
  } catch (err) {
    showError(err.message);
  }
}

init();
