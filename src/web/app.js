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
  pick: $("program-pick"),
  edit: $("edit"),
  cView: $("c-view"),
  editor: $("editor"),
  source: $("source"),
  run: $("run"),
  cancel: $("cancel"),
  buildStatus: $("build-status"),
  buildError: $("build-error"),
  explain: document.querySelector(".explain"),
  explainToggle: $("explain-toggle"),
  explainWhat: $("explain-what"),
  explainContext: $("explain-context"),
  explainLook: $("explain-look"),
  explainDeeperLine: $("explain-deeper-line"),
  explainDeeper: $("explain-deeper"),
  explainDeeperText: $("explain-deeper-text"),
};
const USER_PROGRAM = /^u_[0-9a-f]{16}$/; // names the backend gives typed programs

const state = {
  programName: DEFAULT_PROGRAM, // which program's artifacts to show
  examples: [], // the committed programs, from /api/programs
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

// The page's one way to reach the API: GET, or POST when `send` is given.
async function getJson(path, send) {
  const init = send === undefined
    ? {}
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(send) };
  const resp = await fetch(path, init);
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    // FastAPI's own validation errors give a list; ours give one plain message.
    const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join("; ") : body.detail;
    throw new Error(detail || `request failed: ${resp.status}`);
  }
  return body;
}

function showError(message) {
  // Clear the drawing so a stale result never sits beside an error.
  els.view.replaceChildren();
  for (const node of [els.explainWhat, els.explainContext, els.explainLook]) node.textContent = "";
  els.explainDeeperLine.hidden = true;
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

/**
 * Scroll the asm pane, and only the asm pane, so that row is visible below the
 * sticky header. (scrollIntoView would also scroll the window, pulling a reader
 * who scrolled down to the datapath back up every cycle.)
 */
function keepInPane(row) {
  const pane = els.asm.parentElement;
  const head = els.asm.querySelector("th")?.offsetHeight ?? 0;
  const top = row.getBoundingClientRect().top - pane.getBoundingClientRect().top + pane.scrollTop;
  if (top - head < pane.scrollTop) pane.scrollTop = top - head;
  else if (top + row.offsetHeight > pane.scrollTop + pane.clientHeight) {
    pane.scrollTop = top + row.offsetHeight - pane.clientHeight;
  }
}

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
    if (on) keepInPane(tr);
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

// Text with `backtick` spans shown as code (the backend quotes assembly that way).
function withCode(node, value) {
  node.replaceChildren(
    ...value.split("`").map((part, i) => (i % 2 ? text("code", part) : document.createTextNode(part))),
  );
}

// The backend's plain-language explanation of this cycle, in the bottom panel.
function renderExplanation(e) {
  withCode(els.explainWhat, e.what);
  els.explainContext.textContent = e.context;
  els.explainLook.textContent = e.look_for;
  els.explainDeeperLine.hidden = e.deeper_view === null;
  els.explainDeeperText.textContent = e.deeper ?? "";
  els.explainDeeper.onclick = e.deeper_view === null ? null : () => openView(e.deeper_view);
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
    renderExplanation(cv.explanation);
    renderCrumbs(view);
    await drawModule(els.view, view, openView);
    // Says what is on screen, once it is drawn (the smoke check waits for it).
    if (ticket === state.request) els.view.dataset.drawn = `${state.programName}:${cycle}:${path}`;
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
  // Fit to width and fit to height are alternatives: ticking one unticks the other.
  const fitHeight = $("fit-height");
  const applyFit = () => {
    els.view.classList.toggle("fit", els.fit.checked);
    els.view.classList.toggle("fit-height", fitHeight.checked);
  };
  els.fit.addEventListener("change", () => {
    if (els.fit.checked) fitHeight.checked = false;
    applyFit();
  });
  fitHeight.addEventListener("change", () => {
    if (fitHeight.checked) els.fit.checked = false;
    applyFit();
  });
  const changed = $("show-changed");
  changed.addEventListener("change", () => els.view.classList.toggle("no-changes", !changed.checked));
  document.addEventListener("keydown", (ev) => {
    const typing = [HTMLInputElement, HTMLSelectElement, HTMLTextAreaElement];
    if (typing.some((kind) => ev.target instanceof kind)) return;
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

// --- choosing and typing a program (M5) -------------------------------------------

// Load a program's listing and open it: on `cycle` if given (a link), else
// where the backend says the layers line up.
async function load(name, cycle = null, view = DEFAULT_VIEW) {
  stopPlay();
  state.programName = name;
  state.selectedLine = null;
  state.cv = null;
  state.program = await getJson(`/api/program?${programQuery()}`);
  const golden = await getJson(`/api/golden?${programQuery()}`);
  state.cycles = golden.retired;
  els.slider.max = String(state.cycles - 1);
  renderSource(state.program);
  renderPicker();
  const opening = await getJson(`/api/start?${programQuery()}`);
  const linked = cycle !== null;
  const start = linked ? Math.min(Math.max(cycle, 0), state.cycles - 1) : opening.cycle;
  // Say why only when the page chose the cycle; a link chose it otherwise.
  els.startReason.textContent = linked ? "" : `It opened on cycle ${opening.cycle}, ${opening.reason}.`;
  await show(start, view);
}

// The examples from /api/programs, plus "your program" while one is shown.
function renderPicker() {
  const names = [...state.examples];
  if (!names.includes(state.programName)) names.push(state.programName);
  els.pick.replaceChildren(
    ...names.map((name) => {
      const label = USER_PROGRAM.test(name) ? "your program" : `${name}.c`;
      const opt = text("option", label);
      opt.value = name;
      return opt;
    }),
  );
  els.pick.value = state.programName;
}

function setEditing(on) {
  els.editor.hidden = !on;
  els.cView.hidden = on;
  els.edit.setAttribute("aria-expanded", String(on));
  els.edit.disabled = on;
  els.buildError.hidden = true;
  els.buildStatus.textContent = "";
  if (on) {
    // Start from the program on screen: its source exactly as the backend holds it.
    els.source.value = (state.program?.c_lines ?? []).map((l) => l.text).join("\n") + "\n";
    els.source.focus();
  }
}

async function buildAndRun(ev) {
  ev.preventDefault();
  els.run.disabled = true;
  els.buildError.hidden = true;
  els.buildStatus.textContent = "building: compile, Spike, gate level and RTL ...";
  try {
    const built = await getJson("/api/programs", { source: els.source.value });
    setEditing(false);
    await load(built.program);
  } catch (err) {
    // A rejected program keeps the old program on screen; the message says why.
    els.buildStatus.textContent = "";
    els.buildError.textContent = err.message;
    els.buildError.hidden = false;
  } finally {
    els.run.disabled = false;
  }
}

function wireProgramControls() {
  els.pick.addEventListener("change", () => {
    setEditing(false);
    load(els.pick.value).catch((err) => showError(err.message));
  });
  els.edit.addEventListener("click", () => setEditing(true));
  els.cancel.addEventListener("click", () => setEditing(false));
  els.editor.addEventListener("submit", buildAndRun);
  // Hide shrinks the panel to its first sentence, so more of the drawing shows.
  els.explainToggle.addEventListener("click", () => {
    const collapsed = els.explain.classList.toggle("collapsed");
    els.explainToggle.textContent = collapsed ? "more" : "hide";
    els.explainToggle.setAttribute("aria-expanded", String(!collapsed));
  });
}

async function init() {
  wireControls();
  wireProgramControls();
  try {
    state.examples = await getJson("/api/programs");
    // The URL can name a program, a cycle and a view:
    //   #program=sum&cycle=11&view=top.rv.dp.alu
    const hash = new URLSearchParams(location.hash.slice(1));
    const asked = Number(hash.get("cycle") ?? "x");
    await load(
      hash.get("program") || DEFAULT_PROGRAM,
      Number.isInteger(asked) ? asked : null,
      hash.get("view") || DEFAULT_VIEW,
    );
  } catch (err) {
    showError(err.message);
  }
}

init();
