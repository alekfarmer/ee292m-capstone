# Progress log: M2

EE292M capstone, *C to Gates*. This log covers milestone M2, simulating the
whole core, built on branch `m2-simulation` (on top of M0/M1). As before, I
worked with Claude Code as the coding agent, following `AGENTS.md`: plan
first, approval before work, everything through the Makefile.

## Timeline

| Date | What happened |
| --- | --- |
| 2026-10-14 | Discussed my vision of stepping through cycles (C → asm → binary → gates); agreed it is M2–M4 and chose the tools |
| 2026-10-14 | M2 built, tested and pushed on `m2-simulation` |
| 2026-10-18 | Merged the peer-review response and spelling fix from `m0-m1` into this branch |

## Decisions

- **Two independent simulations.**
  - Yosys `sim` runs the program on the synthesized gate netlist. This is
    what the page shows.
  - Icarus Verilog runs the same program on the SystemVerilog source, as a
    reference used only for checking.

  Icarus over Verilator: Icarus is 4-state, so an uninitialized value shows
  up as `x` instead of a plausible-looking 0, which matters when every
  displayed bit must be right.
- **Icarus Verilog 12.0-2**, pinned to the Debian source version
  (`12.0-2*`), because the binary package suffix differs between arm64 and
  amd64.
- **ALU split into blocks** (`adder32`, `logicunit`, `shifter`, `resultmux`),
  so each can be drawn on its own in M3. Total gates went from 2,191 to 2,169.
- **Register file starts at zero**, as Spike's registers are once `crt0.S`
  has cleared what Spike's boot ROM leaves behind. This avoids `x` values
  spreading through the gates.
- **Sampling:** both runs are read once per cycle, just before the rising
  clock edge, with reset cycles left out, so cycle *n* is instruction *n*
  of Spike's log.

## What was built

- `src/app/simulate.py`: runs both simulations and the checks.
- `src/app/vcd.py`: a VCD reader shared by both simulations.
- `backend/rtl/tb_rtl.sv`: the Icarus testbench.
- `backend/artifacts/trace.json`: every net of the gate netlist in every
  cycle, stored as changes. It holds 1,876 signals (6,059 bits) and is about
  1 MB. Served at `/api/trace`.
- `trace.json` is written **only if every check passes**:

  | Check | Result for `sum.c` |
  | --- | --- |
  | Gate level = RTL, bit for bit, every cycle | 459 shared signals, including every module port |
  | No unknown (x/z) values | none in any of the 57 cycles |
  | PC and instruction match Spike | 57 of 57 |
  | Register writes match Spike | 43 of 43 |
  | x0 always reads 0 | yes |
  | Halt cycle matches Spike | cycle 56 |

- The smoke check also reads the trace from the running app.

## Problems found and fixed

- **`$readmemh` ran during synthesis.** Yosys executes it even when the RAM
  is read as a black box, and failed because no image exists then. Fixed with
  a `SIM_RAM_IMAGE` define that only the two simulations set.
- **`x` values in the gate-level trace.** They came only from temporary nets
  Yosys creates inside the behavioural RAM model, not from the design. Fixed
  by leaving out private nets inside the two behavioural models; their ports
  and named signals stay in.
- **Unhelpful first error.** Both deliberate bugs were first caught by the
  halt-cycle check, which names no signal. Reordered the checks (gate vs RTL,
  then each instruction vs Spike, then the halt), so a failure names the first
  cycle and signal that differ.
- **A slip while undoing a deliberate bug:** a `git checkout` also reverted
  uncommitted edits to `synth.ys`. They were restored, and the stale-artifact
  test confirmed nothing else changed. Since then, work is committed before
  any bug-injection run.

## Verification

- `make verify` (lint, 55 tests, smoke check) is green.
- The tests re-derive every check from the artifacts rather than trusting the
  pipeline's own checks.
- **Deliberate bugs, each caught, then reverted:**

  | Bug | Caught by | Message |
  | --- | --- | --- |
  | `bge` treated as `blt` in the RTL | comparison with Spike | "cycle 11: hardware is at pc=0x8000004c, Spike at pc=0x8000003c" |
  | The adder's XORs turned into ORs in the gate netlist only | gate vs RTL comparison | "gate level and RTL differ in cycle 10 on 78 signals" |

  The first bug can only be caught against Spike, because both simulations run
  the same wrong RTL. The second can only be caught by the gate-vs-RTL
  comparison.
- **Not verified:**
  - Only `sum.c` has been run. Shifts, byte and halfword loads and stores, and
    the less common branches have not been run against Spike yet.
  - No amd64 build, and no `make verify` from a fresh clone.

## What came next

- **M3** (branch `m3-views`): the page uses the trace for linked, steppable
  views. See `docs/progress-m3.md` on that branch.
