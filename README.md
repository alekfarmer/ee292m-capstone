# C to Gates: Watching a RISC-V Program Run All the Way Down

An interactive, browser-based visualization that follows one small C program
through every layer of abstraction: **C → RISC-V assembly → machine code →
datapath → logic gates**. You can step through it cycle by cycle, and at each
layer the values match what the real hardware would produce.

> Status: **M0–M3 done** (gate-level adder spike, software pipeline,
> whole-core simulation, linked steppable views). M4 (gate-level views of
> every module) is next. See `PROMPT.md` for the brief.

## Quick start

You need Docker (running), GNU Make and git. Nothing else is installed on
your machine; every tool runs inside the project's container.

```sh
make build      # first time: ~15-25 min (Yosys and Spike are built from source)
make up         # http://127.0.0.1:8000  (port: APP_PORT in .env, see .env.example)
make down
make verify     # the gate: build, lint, tests, smoke check
make help       # every target
```

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

## What exists now

| Path | What |
|---|---|
| `backend/rtl/` | Single-cycle RV32I core in SystemVerilog, MIT (`docs/core-choice.md`); `synth.ys` |
| `backend/programs/` | `sum.c` (the fixed program), `crt0.S`, `link.ld` (4 KiB RAM at `0x80000000`) |
| `backend/artifacts/` | Generated, committed (below) |
| `src/app/` | Python backend: pipelines and the API (`/docs` lists the endpoints) |
| `src/web/` | The page (plain HTML, JS and SVG) |
| `tests/` | pytest: M0, M1, rejected programs, API |

Artifacts:

| File | Contents |
|---|---|
| `netlist.json` | Yosys JSON netlist, hierarchy kept, gates in {AND, OR, XOR, NOT, MUX, DFF}; register file and RAM are black boxes |
| `gate_counts.json` | Gates per module, local and including submodules |
| `adder_values.json` | Every net in the adder for each input case, from Yosys `sim` on the netlist |
| `program.json` | C lines; asm lines `{addr, hex, text, function, c_line}` |
| `sum.hex` | The whole 4 KiB RAM image, one little-endian word per line (`$readmemh`) |
| `golden.json` | Spike commit log `{pc, insn, rd, rd_value}` from `_start` to the halt |
| `trace.json` | Every net of the gate netlist in every cycle (as changes), plus what was verified |
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
out (elkjs) and draws. Tests check that every wire of every view carries the
trace's value and that every input of every block is drawn connected; the
smoke check loads the real page in headless Chromium and reads a drawn wire.
Shown as blocks only until M4: the ALU shifter and result mux, the load/store
unit, the PC adders, and the ALU's 82 gates of glue logic.

**Rejected programs:** floats, `*` `/` `%`, `#include`, calls into libc or
other undefined functions, images larger than RAM, and programs that do not
halt within 500 instructions each give one clear error (see
`tests/test_rejections.py`).

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

**Audience:** Students interesteded in the whole stack from SW to HW.

**What they decide or learn:** Learn how a processor is implemented with a visual representation.

## Architecture and the backend/frontend boundary

```
 BACKEND (offline, Python + CLI tools)                     FRONTEND (static web app)
 ───────────────────────────────────────────────────┐   ┌──────────────────────────
 compile()     C ──gcc──► ELF ──objdump──► asm, hex │   │ load artifacts
 synthesize()  core.sv ──Yosys──► gate netlist.json │   │ render C / asm / hex panes
 simulate()    netlist + hex ──► per-cycle trace    │   │ render datapath + gate views
 verify()      trace vs. Spike golden log           │   │ step / scrub through cycles
               ──► artifacts/*.json  ───────────────┼──►│ highlight, zoom, link layers
 ───────────────────────────────────────────────────┘   └──────────────────────────
```

**The boundary sits after `simulate()` and `verify()`.** The backend produces
fully evaluated, verified data: every net's value at every cycle. The frontend
is a pure viewer. It reads JSON and draws it, and it never computes a logic
value.

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
