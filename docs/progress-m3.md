# Progress log: M3

EE292M capstone, *C to Gates*. This log covers milestone M3, the linked,
steppable views, built on branch `m3-views` (on top of M2). As before, I
worked with Claude Code as the coding agent, following `AGENTS.md`: plan
first, approval before work, everything through the Makefile.

## Timeline

| Date | What happened |
| --- | --- |
| 2026-10-14 | View choices agreed (generated datapath, elkjs, gate views for small modules, two step modes) |
| 2026-10-17 | Plan approved, with the datapath as the first view; M3 built, checked by screenshot, tested and pushed |
| 2026-10-18 | Merged the peer-review response, spelling fix and progress logs from the earlier branches |
| 2026-10-25 | Round 3 code reviews (suzhao, PR #3; lrusso3, PR #4) built in, ready for the PR to `main` |

## Decisions

- **The page opens on the datapath**, as in the textbook; `top` (core plus RAM)
  is one click up.
- **The datapath is generated from the netlist** rather than hand-drawn. elkjs
  0.12.0 (exact version) runs in the browser and only places boxes and routes
  wires. It computes no values.
- **Everything shown is computed by the backend**, including instruction
  fields, wire values (slices such as `instr[19:15]` included), and the
  targets of "next / previous C line". The page only draws.
- **Gate views** for the small and regular modules: the main and ALU
  decoders, branch unit, controller, muxes, PC register, immediate decoder
  and logic unit, plus the ALU adder in its textbook layout. The larger
  modules stay blocks until M4.
- **Both step modes:** by cycle and by C line.
- **Headless Chromium in the image** (Debian `chromium-headless-shell`,
  about 210 MB). It is only for `make smoke` and `make screenshot`, never
  used by the app. At first it was pinned to its major version (155), because
  Debian's security updates delete old Chromium builds. That pin broke within
  a week (Debian moved to 156), so it is now pinned to an exact build through
  snapshot.debian.org, which keeps every build for good.

## What was built

- **Backend:**
  - `src/app/decode.py`: each instruction's format, fields, bits and meaning,
    added to `program.json`.
  - `src/app/views.py`: `/api/cycle/{n}` (what runs in a cycle, its register
    write, and the C-line step targets) and `/api/view/{path}?cycle=n` (any
    module as a graph of its ports, blocks or gates and wires, each wire with
    its value).
- **Page** (`src/web/`), four panes:
  - C source and assembly, linked: the running line is highlighted, and
    clicking either highlights the other.
  - Machine code: coloured fields with bits and meaning, plus the register
    written.
  - Hardware: the datapath with every wire's value and changed wires
    highlighted. Blocks open into blocks or gates, and breadcrumbs lead back
    up.
- **Stepping:** step by cycle or by C line, a slider, play (1–5 cycles a
  second), and keys. The URL keeps the cycle and view, e.g.
  `#cycle=11&view=top.rv.dp.alu`.
- **`make screenshot`:** saves pictures of six views for checking by eye.
- **Sanity check at cycle 11** (`add a0,a0,a5`, first time through
  `sum += i`):
  - the datapath reads x10 and x15, adds 0 + 1 and writes 1 back to a0;
  - the main decoder's opcode pins read 0110011, and `regwrite` is 1.

## Problems found and fixed (by looking at screenshots)

- **elk crashed** ("Cannot read properties of null"). Ports that weren't on
  blocks were given undefined coordinates. The page showed the error and
  cleared the drawing, as designed. Fixed by setting coordinates only on block
  pins.
- **⏮ / ⏭ didn't render** (missing font glyphs); replaced with plain text.
- **Pin names overlapped block names;** blocks now have a header area with
  pins in rows below it.
- **Ambiguous decoder inputs:** all seven `op` bits left one pin. Modules made
  only of gates now get one labelled pin per bit (`op[0]` … `op[6]`).
- **The "changed" highlight was noisy;** it's now subtler, with a checkbox to
  turn it off.
- **The adder opened at bit 31;** it now scrolls to bit 0, and its margin is
  wider so the carry-out label isn't clipped.

## Verification

- `make verify` (lint, 81 tests, smoke check) is green.
- **Tests:**
  - every wire of every view carries the trace's value, with slices
    recomputed in the test;
  - every input of every block and gate is drawn fully connected;
  - the datapath and the adder view are checked in all 57 cycles;
  - each cycle maps to the right PC, asm line and C line, matching Spike;
  - C-line stepping lands on the first instruction of the next or previous
    line;
  - instruction fields reassemble to each instruction's hex;
  - the API rejects bad paths and cycle numbers.
- **The smoke check renders the real page** in headless Chromium and confirms
  the drawn pc wire shows 0x80000000 in cycle 0, so the frontend is checked
  too.
- **Deliberate bugs, each caught, then reverted:**

  | Bug | Caught by |
  | --- | --- |
  | Wire slices read one bit too high | the per-wire value tests (2 failed) |
  | "Next line" lands on the wrong cycle | the stepping test |
  | The page draws every wire value as 0 (frontend only) | the rendered-page smoke check |

- **Not verified:**
  - Clicking, keys and play aren't tested automatically; I checked six views
    by screenshot, opened through the URL.
  - Only headless Chromium in light mode; not Safari, Firefox or dark mode.
  - The automatic datapath layout has more wire crossings than the textbook
    figure and is wider than one screen ("fit to width" helps).
  - Only `sum.c`.

## Open for M4

- Gate views of the ALU shifter (398 gates), the result mux (439), the
  load/store unit (220), the PC adders (162 each) and the ALU's 82 gates of
  glue logic. All are blocks only today.

## After the round 3 reviews (2026-10-25)

Both reviewers looked at this branch. Every finding was accepted:

- **README opening** (suzhao): who the project is for, and the comparison
  with godbolt, Ripes and Logisim, now come first. The architecture diagram
  now shows the page asking the API rather than loading artifact files.
- **One program per folder** (suzhao): each program's artifacts live in
  `backend/artifacts/<program>/`, and the API takes `?program=`. A new test
  built a second program (`countdown.c`, a0 = 6) next to `sum`. It failed
  before the change (the second program's files would have overwritten the
  first's) and passes after it.
- **The adder's `t` gate** (lrusso3): the `g` wire ran straight through the
  `t` AND gate, so it looked like a three-input gate. A new test that fails
  if any wire enters a gate's body caught this on the old drawing; the wire
  now goes round in a side channel.
- **First screen and plain language** (lrusso3): the page header now says
  who the project is for, and the README opens with a sentence for readers
  outside the field.
- **Organization and interfaces, written down and tested:** README gained a
  "How the code is organized" section (the one pipeline, each module's one
  job, the design patterns by name). A new `tests/test_architecture.py`
  checks the interfaces. It failed first on a real leak: `software.py` started
  Spike itself, bypassing `tools.py`. The streaming run moved into
  `tools.ToolStream`. Along the way, Spike's exit code turned into -13
  (SIGPIPE), because `yield from` closed the pipe when the reader stopped
  early; a plain loop fixed it.
- `make verify` is green with 90 tests.
