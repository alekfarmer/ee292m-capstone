# Work log: round 4 reviews (session 6a, testing and trust)

EE292M capstone, *C to Gates*. This log covers the new version that builds
in the feedback from the session 6a reviews: Su Zhao's (`feedback/20261027_suzhao_afarmer8.md`
and its checklist, PR #6) and Logan Russo's (`feedback/20261030_lrusso3_afarmer8.md`,
PR #9). As before, I worked with Claude Code as the coding agent, following
`AGENTS.md`: plan first, approval before work, everything through the
Makefile. Work is on branch `review-round4`.

## Timeline

| Date | What happened |
| --- | --- |
| 2026-10-27 | Su's review; by email I accepted the main suggestion (open on `sum += i`, add a "start here" sentence) |
| 2026-10-30 | Logan could not run the project on Windows; `.gitattributes` and Windows support built and merged (PR #8), then his review of the merged version recorded the finding |
| 2026-11-01 | Plan approved, with a prebuilt image in GitHub's registry instead of a slimmer local image; everything below built and tested |

## Finding by finding

### 1. The message: the page opened where nothing lines up (suzhao)

**Finding.** The page opened at cycle 0 on `auipc sp,0x1`, start-up code with
no C line, so the first screen showed the one place where the layers do not
line up.

**What changed.** The backend now chooses the opening cycle
(`views.start_cycle`, served by the new `GET /api/start`). The rule works for
any program, not just `sum.c`: the first time the program loops back (a jump
to a lower address between two cycles on C lines), else the first cycle on a
C line, else cycle 0. For `sum.c` that is cycle 11, the first
`add a0,a0,a5` (`sum += i`): the C line, the instruction, its fields and the
ALU (0x0 + 0x1 = 0x1) all light up together. A cycle named in the URL still
wins.

**Tests.** Four new tests:
- `sum.c` opens on cycle 11 at `add a0,a0,a5`, C line 4.
- The rule, re-derived independently from Spike's log, matches.
- The two fallbacks work on made-up runs.
- `/api/start` serves the cycle and returns 404 for an unknown program.

The four tests failed before the change (there was no `/api/start`). The
smoke check now also opens the page with no fragment, then checks the cycle
label, the lit C line, the lit instruction and the reason text. It failed on
a page planted to open at cycle 0 ("the page did not open on cycle 11", "C
line 4 is not highlighted") and passed once it was restored.

### 2. The interface: no "start here" (suzhao)

**Finding.** A newcomer could not tell where to look among four panels.

**What changed.** One sentence beside the hardware view: "Start here: press
line ▶. The highlighted C line becomes the highlighted instruction, and in
the datapath the ALU computes it: a + b = result." It is followed by why the
page opened where it did ("It opened on cycle 11, the first time the program
loops back."), using the backend's reason. `make screenshot` now saves the
first screen (`first-screen.png`), which I checked by eye.

### 3. The tests: the planted bugs protected nothing once reverted (suzhao)

**Finding.** The three planted bugs (`bge` as `blt`, XOR as OR, every wire
drawn as 0) were each caught and then reverted by hand. Su asked whether to
keep them as an automatic check.

**What changed.** `make regression` does this.
- **The answer key** is `src/app/regression_key.py`. For each plant it gives
  the edit, the stage that must catch it (`make artifacts`, `make test` or the
  smoke check) and the message that stage must print, or no stage at all for
  a known blind spot.
- **How it runs.** Each plant is applied to a copy of the repository under
  `backend/build/regression/`, which then runs the stages in order, smoke
  against its own server on port 8001. The working tree is never touched.
- **The plants:**
  - `bge` as `blt` in the RTL is caught by the Spike comparison, "cycle 11:
    hardware is at pc=0x8000004c". The gate level and the RTL agree, because
    both run the same wrong design.
  - XOR as OR is planted in the gate netlist only, by a Yosys `chtype` after
    synthesis. The gate-vs-RTL comparison catches it ("gate level and RTL
    differ").
  - Every wire drawn as 0 is caught only by the smoke check, "the drawn pc
    wire does not show 0x80000000", because every backend number is still
    right.
- **Speed.** All four plants take about 15 seconds, so CI runs it on every
  pull request, on both architectures.
- **Drift.** `tests/test_regression_key.py` fails in `make test` if a plant's
  text no longer occurs exactly once, so the key can't silently stop matching
  the code.

**Seen failing.** With the key deliberately wrong (claiming `make test`
catches the `sra` plant), `make regression` failed: "not caught; the key
says caught at tests", showing the copy's passing smoke output. The first
real run also failed, on a bug in the harness: in a planted copy, the key's
own check fails by design, so it is now left out there. After both, 4 of 4
plants behave as the key says.

### 4. The tests: a wrong program the tests would pass, and a tripwire (lrusso3)

**Finding.** The review form asks for one wrong program the tests would
still pass, and one tripwire any error would move.

**What changed.**
- **The wrong program** is in the answer key as an expected miss: `sra`
  shifting in 0s like `srl`. `sum.c` never runs `sra`, and the gate level and
  the RTL agree on the wrong design, so every stage passes. `make regression`
  checks that this stays true, so the blind spot stays written down until M5
  brings programs that exercise every instruction.
- **The tripwire** is a0 = 55: Spike's exit code, the core's a0 at its halt
  and the smoke check.

The README states both, with a table of the plants.

### 5. Time: the first build took 15-25 minutes on every core (suzhao)

**Finding.** Yosys and Spike are compiled from source, which is a high bar
for a classmate who wants to try the project once.

**What changed.** A prebuilt image in GitHub's container registry, instead of
the slimmer local image in my first plan:
- **`make pull`** downloads it in a few minutes.
- **Its tag is a fingerprint** of every file the image is built from (the
  Dockerfile, both manifests and both locks), so a pulled image always
  matches the checkout. If nothing matches (someone changed `docker/`), it
  says to run `make build`.
- **`make build`** now skips the build when the image already carries this
  checkout's fingerprint. Compose labels every build with it, so a pulled
  image is never rebuilt by `make verify`.
- **CI publishes only verified images.** On main, each architecture's image
  is pushed only after it passed `make verify` and `make regression`, then
  the two are joined under one name.
- **CI is faster.** It pulls the image first, so only changes to `docker/`
  pay for the full build.
- **Weekly full build.** A weekly run always builds from scratch, to catch
  drift in the package archives like the Chromium one in PR #7.

The full app keeps the rule that everything is installed when the image is
built: CI builds the image from the same Dockerfile.

**Seen working locally.** `make build` builds once, then prints "build: the
image already matches docker/ (239f5193da1c)". Before anything is published,
`make pull` says "No prebuilt image matches this checkout's docker/ ... run
'make build'".

### 6. Limits: Windows line endings (lrusso3)

**Finding.** On Windows, git's line-ending conversion makes the byte-for-byte
artifact tests fail although nothing changed.

**What changed (PR #8, already merged).**
- `.gitattributes` (`* text=auto eol=lf`) keeps LF line endings everywhere.
- `tests/test_portability.py` names the real cause if a file still has CRLF.
- The Makefile no longer needs bash.
- The README has a Windows section (Docker Desktop, Git Bash, make through
  winget; no WSL setup).
- CI checks the Windows checkout and the Makefile under Git Bash.

### 7. Question: will M5 programs open on a meaningful cycle? (suzhao)

Yes. The start-cycle rule (finding 1) needs nothing specific to `sum.c`: a
user's program opens on its first loop-back, or on its first cycle on a C
line if it has no loop.

## Verification

- `make verify` is green: lint, 105 tests, and the smoke check ("... page
  renders the datapath with pc = 0x80000000 and opens on cycle 11 with its C
  line lit").
- `make regression`: 4 of 4 plants behave as the answer key says.

## Not verified

- **The registry path end to end.** The publish job runs only on main, so the
  first image appears after this branch is merged. After that, the package
  must be set to Public once in its GitHub settings before anyone can pull it
  without logging in. Until then, `make pull` fails with the message above,
  and CI builds from scratch.
- **The CI workflow changes** run for the first time on this pull request.
- **A newcomer seeing the new first screen.** That is the real test of
  findings 1 and 2. I checked the screenshot myself.
