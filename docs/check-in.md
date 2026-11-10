# Check-in: 2026-11-10

EE292M capstone, *C to Gates*. Measured against the plan (the milestones in
`README.md` and the brief in `PROMPT.md`), with the draft due 30 November.
All six milestones, M0–M5, are merged into `main` (last merge: PR #15,
commit `35db1d6`).

## 1. What works, shown

**The gate, at `35db1d6`, run 2026-11-10** (Docker progress lines left out):

```text
$ make verify
All checks passed!
======================= 216 passed, 1 warning in 10.63s ========================
spot-check: sum: 57 cycles x 57 views: 404472 wires, 89205 gates, 14534 unit outputs (no unit model, so left to Spike: aludec, branchunit, controller, maindec); all match
spot-check: tour: 129 cycles x 57 views: 915384 wires, 201885 gates, 32894 unit outputs (no unit model, so left to Spike: aludec, branchunit, controller, maindec); all match
smoke: ok (5 + 3 = 0x00000008 on the gates, a0 = 55 in Spike and in the core's halt store, 57-cycle trace, page renders the datapath with pc = 0x80000000 and opens on cycle 11 with its C line lit; a shifter stage draws its gates and the register table matches the API, and the bottom panel explains the cycle as the API does; a typed program builds through the API (a0 = 10) and the page shows it)
verify: all green
```

The one warning is a deprecation notice from Starlette's test client.

**The planted defects, same commit and day:** `make regression` plants each
defect in `src/app/regression_key.py` in a copy of the repository and
passes only if the stage the key names catches it.

```text
$ make regression
...
regression: ok: sltu_decoded_as_slt: caught at artifacts; the key says caught at artifacts
...
regression: ok: sra_wrong_on_small_negatives: caught at spotcheck; the key says caught at spotcheck
...
regression: ok: bgeu_as_bge: not caught; the key says not caught (blind spot) (rebuilt differently: gate_counts.json, netlist.json, sum/trace.json, tour/trace.json)
regression: 14 of 14 plants behaved as the answer key says
```

**The result everything rests on:** `sum.c` leaves a0 = 55. Two
independent checks confirm it: Spike's exit code, and the core's own halt
store in the gate-level trace. The trace is written only if the gate level
and the RTL agree on all 1,137 shared signals in every one of the 57
cycles, and every instruction's PC, encoding and register write match Spike.

## 2. What failed, the evidence, and what I changed

| What failed | Evidence | What I changed |
| --- | --- | --- |
| The plan's `-O1` | GCC computed the loop at compile time: `main` became `addi a0,zero,55; ret`, leaving nothing to step through | `-Og`: the loop stays, every instruction maps to a C line, 57 instructions in Spike |
| ABC's gates for the large modules | The shifter (398 gates), the result mux (439) and the load/store unit (220) were piles of gates nobody could follow | Rebuilt them in the RTL from small structural blocks (barrel shifters of `mux2`, a `mux2` tree, store/load align), each view at most 96 gates |
| Synthesis | Yosys deleted the whole core: `top` has no outputs | The RAM and register file are marked `(* keep *)` |
| Planted bugs reverted by hand | Round-4 review (suzhao): once reverted, they protected nothing | `make regression` and the answer key, run in CI on every pull request |
| Typed C could read files | `#include "/work/.env"`: gcc's error message quoted the planted secret | `#` (and `%:`, `??=`), inline assembly and `_Pragma` are refused before any tool runs |
| A commit with a failing test | `make test \| tail` hid the exit code | Output goes to a log file and the exit code is checked |
| `make verify` with Docker stopped (today) | It says no image is published, tries a 15–25 minute build, then blames the manifest and its lock; the real cause, the daemon, is on the first line only | Not changed yet: the `image` target should stop when the daemon is not running and say so |

## 3. What I am cutting, and what the draft still claims

**Cut from the plan:**

- `-O1` (above) and Verilator: the RTL runs in Icarus Verilog, and the gate
  netlist in Yosys `sim`.
- Anything outside the brief's scope stays out: pipelining, caches, M/F/C,
  CSRs, libc.
- No new features before the draft. The time goes into the gaps below and
  into writing.
- The explanation panel at phone width and with a screen reader: not
  tested, and not claimed.

**What the draft still claims, and its limits:**

- Every displayed bit of the committed programs (`sum.c`, `tour.c`) is
  checked in every cycle against the trace or an independent model.
- A typed program passes the same build checks (gate level = RTL = Spike,
  every cycle) but is **not** spot-checked. The draft says so.
- Every RV32I instruction runs (`tour.c`, 37 instructions). That is not
  every case: `bgeu` decided as `bge` is a known blind spot, and the
  decoders have no model.
- It runs on Linux and macOS, amd64 and arm64 (CI). Windows: only line
  endings and the Makefile are checked in CI; the full app has not run there.

## 4. One shortcut to throw away, one part to keep and test

**Throw away: layout tests that read the page's source files.** The round-6
checks in `tests/test_page_layout.py` search the CSS and JS for text. Two
of them failed for their own reasons, one by matching a word in a comment.
They pass when the text is there, not when the page behaves. I will replace
them with checks on the page as rendered in headless Chromium, as the smoke
check already does for wires and the register table.

**Keep and test: the boundary at `verify()`.** The backend writes a trace
only after the gate level, the RTL and Spike agree. The page draws only
what the API serves. That is what makes "every displayed bit is right" a
claim I can test. I keep it and close its known gap: add a `bgeu` with a
negative operand to `tour.c`. Then the `bgeu_as_bge` plant must move in
the answer key from "nothing" to "caught at `make artifacts`". I will show
it failing first.

## Done the same day, after the check-in

Sections 1–4 describe `35db1d6`. The three changes they promise are on this
branch, each with its check seen failing first:

| Change | Commit | Seen failing, then passing |
| --- | --- | --- |
| `make image`, `pull` and `build` stop with "Docker is not running" | `be7ffd0` | `tests/test_makefile.py` runs the real Makefile with a stand-in `docker`: all three targets fell through to a pull or a build before |
| Layout checks in a driven browser, not in the page's files; the editor's *build and run* clicked for the first time | `24fed4e` | Four CSS breakages at once gave four smoke failures ("the C source runs 288 px past its panel", ...); two new plants are caught at smoke |
| A `bgeu` comparing 0xfffffff8 with 253 in `tour.c` (a0 still 157845) | `e6bec77` | `bgeu_as_bge` moved from "not caught" to caught at `make artifacts` |

`make verify` is green: 220 tests, and the spot-check covers `tour.c`'s
130 cycles. `make regression` reports 17 of 17 plants behaving as the key
says. The key needs one blind spot, so it now names a new one: an unknown
opcode executed as a memory write. No compiled program runs one, and the
decoders still have no model, so the section 3 limit stands for them.
