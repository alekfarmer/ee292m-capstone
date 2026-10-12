# C to Gates: Watching a RISC-V Program Run All the Way Down

An interactive, browser-based visualization that follows one small C program
through every layer of abstraction: **C → RISC-V assembly → machine code →
datapath → logic gates**. You can step through it cycle by cycle, and at each
layer the values match what the real hardware would produce.

> Status: planning. See `PROMPT.md` for the agent brief.

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

**What they decide or learn:** Lean how a processor is implemented with a visual representation.

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

## Repository layout (planned)

```
starting_point/        # forked base
backend/
  programs/sum.c       # the fixed demo program
  rtl/                 # chosen RV32I core (+ LICENSE)
  scripts/             # compile, synthesize, simulate, verify
  artifacts/           # generated JSON consumed by frontend (committed)
frontend/              # static web app
tests/
```
