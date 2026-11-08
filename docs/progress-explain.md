# Progress log: each cycle explained in plain words

EE292M capstone, *C to Gates*. This log covers a feature added after M5 on
the same branch, `m5-user-c`, and in the same pull request (#14), as you
asked. A panel pinned to the bottom of the window explains every cycle for
a reader who has never seen assembly.

## Timeline

| Date | What happened |
| --- | --- |
| 2026-11-08 | Plan approved: the panel pinned to the bottom of the window; the same branch and PR as M5; two or three sentences per cycle for a newcomer. Built, tested, regression-checked and pushed |

## Decisions

- **The backend writes the text.** The sentences quote values the trace
  computed (register reads, the ALU's answer, the next PC, control signals),
  so they are results, and results come from the backend (AGENTS.md).
  `/api/cycle/{n}` gains an `explanation`:
  - `what`: what the instruction did, with this cycle's values;
  - `context`: its line of C, or why it has none (start-up code, or code the
    compiler added);
  - `look_for`: where to see it happen on the datapath;
  - `deeper` and `deeper_view`: a view to open for more detail.
- **One sentence pattern per kind of instruction:**
  - ALU with registers, and ALU with a constant;
  - load and store;
  - branch;
  - call, jump and return;
  - `lui`/`auipc`;
  - the halt store.

  Special cases read better in plain words: `addi x, zero, k` "puts the
  number k into x", `addi x, y, 0` "copies y into x", and `jalr zero,0(ra)`
  "returns from the function".
- **How numbers are written.** Addresses in RAM, up to and including the
  stack top, are in hex; other values are in signed decimal, with the hex
  added when the value is large. A register is written with its value:
  "a5 (= 10)".
- **The text names its own evidence.** Each explanation lists the datapath
  block ids and wires its "look for" sentence names. The page prints the
  block ids in brackets ("the ALU (alu)"), so a reader can find each one on
  the drawing.

## Tests (`tests/test_explain.py`, seen failing first)

These run over every cycle of `sum.c` and `tour.c`:
- **The numbers match Spike.** The test rebuilds the register file from
  Spike's commit log and decodes each instruction itself, then checks:
  - each operand and result;
  - load and store addresses;
  - whether a branch is taken;
  - jump targets and return addresses;
  - main's answer at the halt.
- **Named blocks and wires exist.** Every block and wire the text names
  exists on the datapath drawing, and appears in the text.
- **Control values are right.** Every value the text states ("alusrc is 1",
  "pcsrc is 2", "regwrite is 0") matches what the RV32I specification says
  that instruction sets. The test requires more than 100 such statements.
- **The other parts hold up:**
  - each explanation's "go deeper" view exists;
  - the C line is quoted;
  - every kind of explanation is used.
- **One sentence checked word for word.** The sentence for `sum.c` cycle 11
  was worked out by hand: "adds a0 (= 0) and a5 (= 1) and saves the result,
  1, in a0".

Failures found while building it, each fixed in the explainer:
- a shift by a register did not name that register;
- `immext (from ext)` did not name the block the way the page does;
- the stack top, 0x80001000, one past the end of RAM, was written as
  -2147479552.

`make smoke` now also checks that the panel shows the API's sentence, on
`sum.c`'s first screen and on a typed program.

## Regression key (14 plants)

- `explanation_branch_backwards`: the explainer says "taken" when a branch
  is not. Caught at tests.
- `explanation_not_drawn`: the page never fills in the panel. Caught at
  smoke.

## Known limits

- **"Look for" always describes the datapath,** even when you have opened a
  block such as the ALU. Tailoring it to the open view would be a follow-up,
  and so would lighting up the named blocks on the drawing.
- **English only.**
- **The panel's collapsed state is not remembered** across reloads.
- **Not tried at phone width,** and not read with a screen reader. The
  panel is marked `aria-live="polite"`.
