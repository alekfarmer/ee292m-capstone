# Progress log: M0 and M1

EE292M capstone, *C to Gates*. This log covers the first implementation:
milestones M0 (gate-level spike) and M1 (software pipeline), built on branch
`m0-m1` and merged into `main` as PR #2. I did the work with Claude Code as
the coding agent, following `AGENTS.md`. The agent posted a plan before every
multi-file change and waited for my approval, and everything ran through the
Makefile, inside the container.

## Timeline

| Date | What happened |
| --- | --- |
| 2026-10-11 | Starting point on `main`: README (plan and milestones), AGENTS.md, ARCHITECTURE.md, PROMPT.md |
| 2026-10-14 | Peer review of the plan by Logan Russo (lrusso3), merged as PR #1 |
| 2026-10-14 | Core choice, tool pins and plan agreed; M0 and M1 built, tested and committed on `m0-m1` |
| 2026-10-18 | Responded to the review, fixed spelling, merged `main` into `m0-m1`; PR #2 opened and merged |

## Decisions

- **Core: our own single-cycle RV32I core, MIT licensed.** It follows the Harris & Harris
  *DDCA RISC-V Edition* chapter 7 design and module names, extended to the full
  RV32I base. I could not find an openly licensed copy of the textbook HDL, and
  the textbook core implements only about ten instructions, too few for
  `sum.c`. Details in `docs/core-choice.md`.
- **Not CVA6.** I asked about it. It is a 6-stage, application-class core (MMU,
  caches, CSRs) with far more gates, and with several instructions in flight
  per cycle it breaks the "one instruction, one cycle" story. It was rejected
  for this project.
- **Plain SVG for the M0 adder, not netlistsvg.** The ripple-carry adder is
  regular, so a hand layout reads like the textbook and gives exact net IDs to
  test against. Automatic layout (ELK) is left for irregular modules in later
  milestones.
- **Pinned tools** (in `docker/Dockerfile`, recorded in `backend/artifacts/toolchain.json`):

  | Tool | Pin |
  | --- | --- |
  | Yosys | 0.68, built from tag |
  | Spike | commit `f8a060b`, built from source |
  | RISC-V GCC | 14.2.0+19 (Debian trixie) |
  | binutils | 2.44-3+7+b1 (Debian trixie) |
  | Python | 3.14 |

- **`-Og` instead of `-O1`.** At `-O1` GCC computes the loop at compile time and
  `main` becomes `addi a0,zero,55; ret`, leaving nothing to visualize. `-Og`
  keeps the loop, with every instruction mapped to a C line (57 instructions
  in Spike).

## What was built

- **M0:**
  - Yosys synthesis keeping hierarchy, mapped to {AND, OR, XOR, NOT, MUX, DFF},
    with the register file and RAM as black boxes: 2,191 gates in total.
  - The ALU adder is a structural ripple-carry chain of 32 full adders,
    excluded from ABC so each bit stays 2 XOR + 2 AND + 1 OR (160 gates).
  - A page draws the adder at gate level with values from Yosys `sim`:
    5 + 3 = 0x00000008 with carry 0, and 0xFFFFFFFF + 1 = 0 with carry 1.
- **M1:** `make artifacts` compiles `sum.c` with a minimal `crt0.S` and linker
  script, then writes:
  - `program.json`: the asm listing, with each line mapped to its C line;
  - `sum.hex`: the RAM image;
  - `golden.json`: Spike's commit log. a0 = 55 at the halt, and Spike exits with code 55.
- **Rejected inputs:** floats, `*` `/` `%`, `#include`, libc calls, images
  larger than RAM, and programs that do not halt within 500 cycles each give
  one clear error.

## Problems found and fixed

- **Docker was not running** at the start: the lock step failed until I started Docker Desktop.
- **Synthesis deleted the whole core.** `top` has no outputs, so Yosys saw
  nothing as used. Fixed by marking the RAM and register-file instances `(* keep *)`.
- **`-O1` folded the loop away** (above). Both alternatives were tried before
  choosing `-Og`.
- **Round-trip test mismatch.** objdump prints jump targets as `0x80000030`
  without symbols and `80000030 <main>` with them; normalized both.
- **The adder drawing was ambiguous** where wires cross versus branch.
  Junction dots were added, with a test that every fan-out net has one.

## Verification

- `make verify` (lint, 44 tests, smoke check) is green.
- **Required checks that pass as tests:**
  - Spike `a0 == 55`;
  - every asm line round-trips hex ↔ text;
  - the two reference encodings (`0x00000513`, `0x00b50533`);
  - the rendered adder reads `0x00000008` / carry 0 and `0` / carry 1;
  - the gate-count report lists ALU, decoder, control and top level.
- **Each pipeline's test was shown failing on a deliberate bug:** an OR in
  place of the full adder's sum XOR, and `i < 10` in `sum.c`. 11 tests failed;
  both bugs were reverted.
- **Tests also fail if the committed artifacts are stale.**
- **Not verified:** `make verify` from a fresh clone, and an amd64 build (only
  built on Apple Silicon).

## Peer review

- One review (lrusso3, PR #1): 5 of 5 checklist items, no defects found.
- Its one suggestion, broader and more customizable inputs, is **deferred to
  M5**, with the reason recorded in README's "Review feedback" section: every
  displayed bit must first be verified for one fixed program.
- Spelling fix: "interesteded" → "interested" in README.md and PROMPT.md.

## What came next

- **M2** (branch `m2-simulation`): whole-core simulation at gate level and RTL,
  checked against Spike every cycle.
- **M3** (branch `m3-views`): linked, steppable C / asm / machine-code /
  hardware views.
- **Open for M4:** gate-level views of the larger modules (shifter, result
  mux, load/store unit, PC adders).
