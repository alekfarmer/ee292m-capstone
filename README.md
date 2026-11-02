# C to Gates: Watching a RISC-V Program Run All the Way Down

An interactive, browser-based visualization that follows one small C program
through every layer of abstraction: **C → RISC-V assembly → machine code →
datapath → logic gates**. You can step through it cycle by cycle, and at each
layer the values match what the real hardware would produce.

**Who it is for:** students interested in the whole stack from software to
hardware, who want to see how a processor is implemented, layer by layer, with
a visual representation.

**In plain terms:** a computer runs a program by switching tiny on/off
circuits called logic gates. This tool lets you watch one small program (adding
the numbers 1 to 10) do exactly that, one step at a time, from the code a person
writes all the way down to the individual gates.

## Why this is worth doing

Students learn each layer in a different course: C in intro programming,
assembly in computer organization, datapaths in architecture, gates in digital
logic. They rarely see **one** program cross **all** of these boundaries
without a gap. Existing tools each cover only part of the stack:

| Tool | C | Asm | Datapath | Gates |
|---|---|---|---|---|
| Compiler Explorer (godbolt) | ✅ | ✅ | – | – |
| Ripes / Venus / RARS | partial | ✅ | ✅ (Ripes) | – |
| Logisim / Digital / DigitalJS | – | – | manual | ✅ |
| **This project** | ✅ | ✅ | ✅ | ✅ |

The goal is that a viewer can click the `+` in `sum += i`, follow it to the
`add` instruction, then to the ALU, then to the full adder computing bit 3,
and see the actual 0s and 1s at that cycle.

> Status: **M0–M3 done** (gate-level adder spike, software pipeline,
> whole-core simulation, linked steppable views). M4 (gate-level views of
> every module) is next. See `PROMPT.md` for the brief.

## Quick start

You need Docker (running), GNU Make and git. Nothing else is installed on
your machine; every tool runs inside the project's container. It runs on
Linux, macOS and Windows, on Intel/AMD (amd64) and ARM (arm64, including
Apple silicon) machines; the image is built natively for yours. On Windows,
see [Windows](#windows) first.

```sh
make pull       # first time: a few minutes (downloads the image CI built and verified)
make build      # or build it yourself: ~15-25 min (Yosys and Spike from source)
make up         # http://127.0.0.1:8000  (port: APP_PORT in .env, see .env.example)
make down
make verify     # the gate: build, lint, tests, smoke check
make help       # every target
```

`make pull` needs no account. It takes only the image built from exactly this
checkout's `docker/` files; if there is none (you changed `docker/`), it says
so, and `make build` builds it. `make build` skips the build when the image
there already matches.

The page follows `sum.c` cycle by cycle:

- **C source** and **assembly**, linked: the running line and instruction are
  highlighted; click a C line to highlight its instructions, or the reverse.
- **Machine code**: the current instruction's fields (opcode, rd, rs1, ...)
  with their bits and meaning, and the register it writes.
- **Hardware**: opens on the datapath, generated from the synthesized netlist,
  with every wire's value in this cycle (buses show their value; 1-bit wires
  are coloured 1/0; wires that changed are highlighted). Click a block marked
  ⤢ to open it: the ALU into its blocks, the ALU adder into its 160 gates
  (textbook layout), and the decoders, muxes, PC register and immediate
  decoder into their gates. Hover any wire for its name and value.
- **Stepping**: by cycle or by C line, a slider, play (1–5 cycles a second),
  and keys (← → cycle, ↑ ↓ C line, Home/End, space = play). The URL keeps the
  cycle and view, e.g. `#cycle=11&view=top.rv.dp.alu`.

`make screenshot` saves pictures of a few views to `backend/build/screenshots/`.

`make artifacts` regenerates everything in `backend/artifacts/` from the
sources; the generated files are committed, and the tests fail if they are
stale.

### Windows

No WSL setup or Linux shell of your own is needed. You need three things:

1. **Docker Desktop**, installed and running. It manages its own Linux
   backend; you never work inside it.
2. **Git for Windows** (`winget install Git.Git`). It includes **Git Bash**,
   which provides the shell and small tools (`sh`, `id`, `tr`, `sed`, ...)
   the Makefile uses.
3. **GNU Make** (`winget install ezwinports.make`), then open a new Git Bash
   window so it is on the path.

Run every `make` command from **Git Bash**, not from PowerShell or cmd.

The repository's `.gitattributes` keeps Mac/Linux (LF) line endings on every
machine, which the tests need. A clone made before that file was added keeps
Windows endings; delete it and clone again. `make test` names any file with
Windows endings.

CI runs `make verify` on Linux amd64 and arm64 for every pull request, and
checks the Windows line endings and the Makefile under Git Bash. The full app
on Windows has not been run by CI: GitHub's Windows machines cannot run Linux
containers.

## What exists now

| Path | What |
|---|---|
| `backend/rtl/` | Single-cycle RV32I core in SystemVerilog, MIT (`docs/core-choice.md`); `synth.ys` |
| `backend/programs/` | `sum.c` (the fixed program), `crt0.S`, `link.ld` (4 KiB RAM at `0x80000000`) |
| `backend/artifacts/` | Generated, committed (below) |
| `src/app/` | Python backend: pipelines and the API (`/docs` lists the endpoints) |
| `src/web/` | The page (plain HTML, JS and SVG) |
| `tests/` | pytest: M0-M3, rejected programs, API, architecture, portability |

Artifacts. The hardware ones sit in `backend/artifacts/`; each program's sit in
a folder named after it (`backend/artifacts/sum/` for `sum.c`), so programs never
overwrite each other:

| File | Contents |
|---|---|
| `netlist.json` | Yosys JSON netlist, hierarchy kept, gates in {AND, OR, XOR, NOT, MUX, DFF}; register file and RAM are black boxes |
| `gate_counts.json` | Gates per module, local and including submodules |
| `adder_values.json` | Every net in the adder for each input case, from Yosys `sim` on the netlist |
| `sum/program.json` | C lines; asm lines `{addr, hex, text, function, c_line}` |
| `sum/sum.hex` | The whole 4 KiB RAM image, one little-endian word per line (`$readmemh`) |
| `sum/golden.json` | Spike commit log `{pc, insn, rd, rd_value}` from `_start` to the halt |
| `sum/trace.json` | Every net of the gate netlist in every cycle (as changes), plus what was verified |
| `toolchain.json` | The version each tool reports |

Gate counts (including submodules; register file and RAM count as 0):

| Part | Module | Gates |
|---|---|---|
| Top level | `top` | 2169 |
| Control unit | `controller` | 78 |
| Main decoder | `maindec` | 39 |
| ALU decoder | `aludec` | 25 |
| Datapath | `datapath` | 2091 |
| ALU | `alu` | 1175 |
| ALU adder | `adder32` | 160 = 32 x (2 XOR + 2 AND + 1 OR) |
| ALU logic unit | `logicunit` | 96 |
| ALU shifter | `shifter` | 398 |
| ALU result mux | `resultmux` | 439 |

`gate_counts.json` breaks every module down by gate type.

**Compile flags:** `-march=rv32i -mabi=ilp32 -Og -g -nostdlib -ffreestanding`.
The brief suggested `-O1`, but at `-O1` GCC computes the loop at compile time
and `main` becomes `addi a0,zero,55; ret`, leaving nothing to visualize. `-Og`
keeps the loop (`add a0,a0,a5` / `addi` / `bge`) with every instruction
mapped to a C line, and Spike retires 57 instructions.

**Whole-core simulation (M2):** the program runs on the synthesized gate
netlist (Yosys `sim`) and, independently, on the SystemVerilog source (Icarus
Verilog). `trace.json` is written only if, for all 57 cycles of `sum.c`:
gate level and RTL agree on every signal they share (459, including every
module port); no net is x or z; every instruction's PC, encoding and
register write match Spike; x0 reads 0; and the core halts in the same cycle
as Spike. The trace holds all 1,876 nets (6,059 bits), about 1 MB.

**Views (M3):** the backend builds every view (`/api/cycle/{n}`,
`/api/view/{path}?cycle=n`) from the netlist and the verified trace, including
the value of each partial bus such as `instr[19:15]`; the page only lays them
out (elkjs) and draws. The page opens on the cycle `/api/start` names: the first time
the program loops back (for `sum.c`, cycle 11, the first `sum += i`, where the
C line, the instruction and the ALU light up together), else the first cycle
on a C line, else cycle 0. Tests check that every wire of every view carries the
trace's value and that every input of every block is drawn connected; the
smoke check loads the real page in headless Chromium and reads a drawn wire.
Shown as blocks only until M4: the ALU shifter and result mux, the load/store
unit, the PC adders, and the ALU's 82 gates of glue logic.

**Planted defects (`make regression`):** each defect in the answer key,
`src/app/regression_key.py`, is planted in a copy of the repository, which
then runs `make artifacts`, `make test` and the smoke check. It passes only if
the stage the key names fails, with the message the key names:

| Plant | Caught by | Why that one |
|---|---|---|
| `bge` taken as `blt` in the RTL | `make artifacts`: "cycle 11: hardware is at pc=0x8000004c" (Spike) | Gate level and RTL run the same wrong design and agree |
| XOR as OR in the gate netlist's full adders | `make artifacts`: "gate level and RTL differ" | The RTL is still right |
| Every wire drawn as 0 on the page | smoke: "the drawn pc wire does not show 0x80000000" | Every backend number is still right |
| `sra` shifts in 0s like `srl` | nothing (a known blind spot) | `sum.c` never runs `sra`; programs that exercise every instruction come with M5 |

The tripwire almost any wrong result moves is a0 = 55: Spike's exit code, the
core's a0 at its halt in the gate-level trace (`test_m2_trace.py`), and the
smoke check.

**Rejected programs:** floats, `*` `/` `%`, `#include`, calls into libc or
other undefined functions, images larger than RAM, and programs that do not
halt within 500 instructions each give one clear error (see
`tests/test_rejections.py`).

## Review feedback

Peer reviews arrive as pull requests into `feedback/` and are merged there.
Accepted findings are built in; each finding pushed back on gets one line
below, with the reason.

- Broader inputs (lrusso3, PR #1): deferred to M5, because every displayed bit must first be verified for one fixed program (M2–M4); the M1 pipeline already accepts any C file in the supported subset and rejects the rest with a clear error.

Round 3 (code reviews of `m3-views`; every finding accepted and built in, none
pushed back on):

- Who the project is for came only after the quick start (suzhao, PR #3): it now opens the README, with the comparison with other tools.
- Artifact names assumed one program (suzhao, PR #3): each program's artifacts now live in their own folder (`backend/artifacts/sum/`), the API takes `?program=`, and a test builds a second program next to `sum`.
- The diagram showed the page loading artifacts (suzhao, PR #3): it now shows the page asking the API.
- The adder's `t` gate was hard to read (lrusso3, PR #4): the `g` wire ran through it, making it look like a three-input gate; it now goes round, and a test fails if any wire crosses a gate.
- No statement for readers outside the field (lrusso3, PR #4): the README now opens with a plain-language sentence, and the page's first screen says who it is for.

Answers to the reviewers' questions (suzhao, PR #3):

- In M5, a user's program will be compiled and simulated live on the server, and its trace shown only after it passes the same checks as `sum.c` (gate level vs RTL vs Spike).
- `views.py` will be split when M4 adds the gate views of the large modules.

Round 4 (session 6a, testing and trust: suzhao, PR #6; lrusso3, PR #9; every
finding built in, none pushed back on; what changed is in
`docs/progress-review-round4.md`):

- The message: the page opened on start-up code, where nothing lines up (suzhao): it now opens on cycle 11, the first `sum += i`, chosen by the backend (`/api/start`), and the smoke check fails unless that cycle's C line and instruction are lit.
- The interface: no "start here" (suzhao): one sentence beside the hardware view says what to press and what to watch, and why the page opened where it did.
- The tests: the planted bugs were reverted by hand and protected nothing afterwards (suzhao): `make regression` plants all three, plus a known blind spot, and checks each against an answer key; CI runs it on every pull request.
- The tests: one wrong program the tests would still pass, and one tripwire (lrusso3): `sra` broken (`sum.c` never runs it), kept in the answer key as an expected miss; the tripwire is a0 = 55.
- Time: the first build took 15-25 minutes on every core (suzhao): `make pull` downloads the image CI built and verified, in a few minutes; `make build` remains for changes to `docker/`.
- Limits: on Windows, git's line-ending conversion would fail the byte-for-byte artifact tests (lrusso3): `.gitattributes` keeps LF everywhere (PR #8), and a test names the cause if not.
- Question, will M5 programs open on a meaningful cycle? (suzhao): yes, by the same rule: the first loop-back, else the first cycle on a C line.

## Architecture and the backend/frontend boundary

```
 BACKEND (Python + CLI tools)                              FRONTEND (static page)
 ───────────────────────────────────────────────────┐   ┌──────────────────────────
 offline (make artifacts):                          │   │
 compile()     C ──gcc──► ELF ──objdump──► asm, hex │   │
 synthesize()  core.sv ──Yosys──► gate netlist.json │   │
 simulate()    netlist + hex ──► per-cycle trace    │   │
 verify()      trace vs. Spike golden log           │   │
               ──► backend/artifacts/*.json         │   │
 serving (API):                                     │   │
 api.py → pipeline.get_* → views.py ────────────────┼──►│ fetch /api/cycle, /api/view
   per-cycle views built from the artifacts         │   │ lay out (elkjs) and draw
                                                    │   │ step / scrub, link panes
 ───────────────────────────────────────────────────┘   └──────────────────────────
```

**The boundary sits after `simulate()` and `verify()`.** The backend produces
fully evaluated, verified data: every net's value at every cycle, served
through the API. The frontend is a pure viewer. It asks the API for a view and
draws it, and it never computes a logic value.

**What breaks if it were drawn one function earlier** (the backend ships only
the netlist, and the frontend simulates it):

1. **Verification stops covering what users see.** `verify()` checks the
   backend's simulation against Spike. If the browser runs its own simulator,
   the values on screen come from code that was never checked. A bug in the JS
   evaluator (signedness, bit ordering, X/uninitialized handling, reset
   behavior) would show wrong gate values while every test passes.
2. **Two simulators to keep in sync.** The JS evaluator would have to match
   Verilator/Yosys semantics exactly and forever.
3. **Performance moves to the client.** Evaluating thousands of gates per cycle
   for hundreds of cycles, plus scrubbing backward in time, requires
   snapshotting state in the browser. Precomputed traces make "jump to cycle
   N" a plain array lookup.

The cost of this boundary is size. Per-cycle values for every net can get big,
so the trace is stored as value *changes* (VCD-style), not full snapshots, and
the first slice limits the program to under 500 cycles.

*Future note:* supporting user-entered C (M5) adds a compile+simulate service
on the backend. The boundary does not move: the frontend still only renders.

## How the code is organized

**One pipeline for the data.** A C file goes through the steps once, in order,
and every value the page shows comes out of the end of it:

```
sum.c ─► software.py ─► program.json, sum.hex, golden.json (Spike)
                         │
synth ─► hardware.py ─► netlist.json
                         ▼
         simulate.py ─► trace.json   (gate-level run; the RTL run and Spike only check it)
                         ▼
         views.py ─► pipeline.get_* ─► api.py ─► the page (draws only)
```

**Modules, one job each** (`src/app/`, `src/web/`):

| Module | Its one job |
|---|---|
| `pipeline.py` | The entry points: one `build_*` per pipeline step, one `get_*` per API endpoint |
| `api.py` | HTTP routes, nothing else |
| `cli.py` | The command line (`make artifacts`, `make preview`) |
| `software.py` | Compile, disassemble and image the C program; run it on Spike |
| `hardware.py` | Synthesize the core with Yosys; count gates; evaluate the adder |
| `simulate.py` | Run the whole core (gate level and RTL) and check it against Spike |
| `vcd.py` | Read the simulators' waveform files |
| `decode.py` | Split an instruction word into its fields |
| `views.py` | Build what the page draws for one cycle (cycle view, module graphs) |
| `render.py` | Draw the adder in its textbook layout (SVG) |
| `tools.py` | Start external programs (gcc, Spike, Yosys, Icarus, Chromium) |
| `models.py` | The typed shape of every artifact and API response |
| `errors.py`, `paths.py` | Error types; fixed locations |
| `smoke.py`, `pagecheck.py` | Check the running app and its rendered page |
| `regression.py`, `regression_key.py` | `make regression`: plant each defect in the answer key, check what catches it |
| `app.js`, `graph.js` | The page: panes and stepping; layout and drawing of module views |

**Design patterns and interfaces.** Each module talks to the others through
one narrow interface, and `tests/test_architecture.py` fails if one reaches past it:

- **Facade:** `pipeline.py` is the only door into the steps behind it.
- **Adapters:** `api.py` (HTTP) and `cli.py` (command line) only translate a
  request into a `pipeline` call. They import nothing else but the shared
  types, errors and paths.
- **One wrapper for external tools:** only `tools.py` starts programs
  (`run_tool` runs to completion; `ToolStream` reads Spike's log as it comes).
  No shell, always a timeout, one error type.
- **Typed contracts:** `models.py` (pydantic) defines every artifact and
  response; `/docs` is the API contract.
- **Precompute, then look up:** everything costly runs offline in
  `make artifacts`, so serving a cycle is a lookup.
- **The page:** one `state` and one `show(cycle, view)` refresh every pane;
  one fetch helper, used only for `/api/`; a request counter drops stale
  responses. Panes never talk to each other.
- **Direction:** the page → `api.py` → `pipeline.py` → the steps → `tools.py`.
  Calls go down, never back up.

## Milestones

Riskiest first. Each milestone ends with a check that can be run.

| # | Milestone | Done when |
|---|---|---|
| **M0** | **Gate-level spike (riskiest).** Synthesize the chosen core with Yosys, keeping module hierarchy, and render only the ALU's adder as gates in a browser page. | Gate count per module is reported; a 32-bit add of 5+3 shows correct values on the adder gates. |
| M1 | **Software pipeline.** Fixed C program → RV32I ELF → asm listing + hex image; Spike golden commit log. | `a0 == 55` at exit in Spike; asm/hex regenerated from one command. |
| M2 | **Hardware simulation.** Run the hex image on RTL and on the gate netlist; emit trace JSON. | Register-file writes match Spike for every retired instruction; gate-level sim equals RTL sim bit-for-bit every cycle. |
| M3 | **Linked layer views.** C, asm, hex, and datapath panes; stepping highlights the active line and active datapath wires in all panes. | Clicking a C line highlights its asm lines (via DWARF line info) and vice versa. |
| M4 | **Drill-down to gates.** Datapath → module (ALU, decoder, register file) → gates, with live values at the current cycle. | Every displayed bit matches the trace; spot-check script passes. |
| M5 | *(Stretch)* **User-entered C** within a defined subset; rejected inputs give clear errors. | Test suite of accepted and rejected programs passes. |

## Top risks

1. **Gate count and visual clutter.** Even a minimal RV32I core synthesizes to
   thousands of gates, and the register file alone is 1,024 flip-flops plus
   large read multiplexers. *Mitigation:* hierarchical drill-down only; never
   draw the whole core flat; treat the register file and memories as
   black-box blocks with values shown, not gates.
2. **Synthesis destroys readable structure.** Optimizers (ABC) turn a clean
   ripple-carry adder into unrecognizable logic, and flattening loses module
   names. *Mitigation:* keep hierarchy (no `flatten`), map to a small gate
   library (AND/OR/XOR/NOT/MUX), and if needed use a hand-written structural
   ALU so the gates match the textbook picture.
3. **Choosing the wrong core.** Production cores (PicoRV32, SERV, VexRiscv) are
   multicycle, bit-serial, or heavily parameterized, and their structure won't
   match how the course teaches datapaths. *Mitigation:* prefer a
   single-cycle RV32I teaching core, e.g. the Harris & Harris *Digital Design
   and Computer Architecture, RISC-V Edition* design. Confirm its license.
4. **Mapping C to hardware events.** `-O0` code is verbose, `-O2` code
   reorders and hides the source structure. *Mitigation:* pick one
   optimization level (e.g. `-O1`) and use DWARF line tables for C↔asm mapping.
5. **Toolchain friction.** Getting the RISC-V GCC, Spike, Yosys, and Verilator
   to install the same way on every machine. *Mitigation:* pin versions in a
   Dockerfile or Nix shell in M1; commit generated artifacts so the frontend
   runs without the toolchain.

## Out of scope (for now)

Pipelining and hazards, caches, the M/F/C extensions, interrupts and CSRs, an
OS or libc, `printf`/I/O, timing and physical design (no transistors or
layout), and compiling C in the browser.

## Repository layout

See "What exists now" above and `ARCHITECTURE.md`, which describes how the
project is built and is kept up to date.
