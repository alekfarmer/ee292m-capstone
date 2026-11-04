# Progress log: M4

EE292M capstone, *C to Gates*. This log covers milestone M4, the drill-down
to gates, built on branch `m4-gates` (on top of `main` after review round 4).
As before, I worked with Claude Code as the coding agent, following
`AGENTS.md`: plan first, approval before work, everything through the
Makefile.

## Timeline

| Date | What happened |
| --- | --- |
| 2026-11-03 | Plan approved: register file as a table (no gates), spot-check on every cycle in `make verify`, no module left as a box; M4 built, tested, regression-checked and pushed |

## Decisions

- **Restructure the RTL rather than draw ABC's output.** Flattened by ABC,
  the shifter (398 gates), the result mux (439) and the load/store unit (220)
  were piles of gates nobody could follow. Each is now built from small
  structural blocks that look like the textbook ones:
  - the shifter: three barrel shifters (`shiftleft`, and `shiftright` twice,
    with fill 0 or the sign bit), each five stages of `mux2`;
  - the result mux: a tree of eight `mux2`s on the `alucontrol` bits;
  - the load/store unit: `storealign`, `loadalign` (two `mux2` stages that
    shift the word right by the byte offset) and `loadextend`;
  - the ALU's own logic: `binvert` (32 XOR) and `zerodetect` (an OR tree),
    leaving 11 gates;
  - the PC adders: `adder32` ripple-carry chains, so they open to the adder
    drawing.

  The core went from 2,169 to 2,045 gates, and no module has more than 96
  gates of its own. Gate level, RTL and Spike still agree on every cycle.
- **The register file is a table, not gates.** As gates it would be about
  1,024 flip-flops and some 2,000 muxes, doubling the netlist. It stays a
  black box in synthesis and opens to its 32 registers, the ones the read
  ports select, and the value stored at the clock edge.
- **The spot-check checks every cycle.** It takes about 6 s for `sum.c`, so it
  runs in full in `make verify`.
- **`views.py` became a package** (`src/app/views/`), as promised in round 3.

## What was built

- RTL: `shiftleft.sv`, `shiftright.sv`, `storealign.sv`, `loadalign.sv`,
  `loadextend.sv`, `binvert.sv`, `zerodetect.sv`. `shifter.sv`,
  `resultmux.sv`, `lsu.sv`, `alu.sv` and `datapath.sv` are rewritten, and
  `adder.sv` is gone.
- `src/app/views/registers.py` and the `registers` view kind, drawn as a
  table by `graph.js`.
- `src/app/spotcheck.py` and `make spot-check`: for every view in every
  cycle it checks wires against the trace, gates against their function, the
  adder drawings, and the register table. It also checks every datapath unit
  instance against an independent RV32I model (`MODELS`). For `sum.c` that
  is 404,472 wires, 89,205 gates and 14,534 unit outputs.
- `make regression` has a spot-check stage and two new plants.
- Smoke reads the drawn register table and checks that a shifter stage draws
  its gates.

## Seen failing before passing

- `sra_as_srl` (the round-4 blind spot): caught by the spot-check at cycle 55,
  "rv.dp.alu.sh.y_sra (shifter) is 0x8000, should be 0xffff8000".
- A register view with rd1 and rd2 swapped (planted by hand, then reverted):
  two tests in `tests/test_m4_gates.py` failed.
- `registers_drawn_as_zero` (new plant): caught at smoke, "the register table
  shows other values than the API".
- The spot-check's first run reported 1,454 problems. They were all its own
  bug: the one-bit full adder's model used a 32-bit add. It was fixed in
  the model, not the design.

## Stage labels (added after M4, same branch)

After a question about multi-cycle processors, we kept the single-cycle
core and labelled the five textbook stages on the datapath instead. The
backend assigns each block its stage, as in the P&H and H&H figures: `rf` in
ID, `pcmux` in IF, the branch-target adder in EX. The page draws the stages
as five columns with bands, plus a note that all five happen in one clock
cycle. Seen failing first: `tests/test_stages.py` failed (no stage data)
before the backend had it. The plant `lsu_without_a_stage` is caught at
tests, and smoke checks that the five bands are drawn in order.

## Known limits

- **The decoders have no model.** `maindec`, `aludec` and `branchunit` are
  checked only through Spike, for the instructions the program runs. The new
  plant `sltu_decoded_as_slt` passes every stage; programs that run every
  instruction (M5) will close this.
- **Two unreachable behaviours changed with the RTL:** `alucontrol` codes
  1010-1111 now give a right shift instead of 0, and a misaligned halfword or
  word load takes the bytes at the offset. Neither can happen in a legal run.
- **Large gate views are long rather than wide.** A 32-bit `mux2` is 32 MUX
  gates in a column, in elk's order rather than bit order (as in M3).

## After review: stale page code and wire colours

- The browser kept running an old `graph.js` after the stage labels landed,
  so the user saw no bands until a hard reload. The page's own files are now
  served with `Cache-Control: no-cache`: a browser may keep them but must ask
  before each use, and an unchanged file costs a 304. The vendored elkjs is
  pinned at image build, so it stays cacheable. Seen failing first:
  `test_page_files_are_revalidated_so_an_update_is_never_stale`.
- A 0 wire was blue-grey and hard to tell from a bus. It is now a neutral
  grey (`#c2c0b8` light, `#4b4a46` dark), with no blue in it.
