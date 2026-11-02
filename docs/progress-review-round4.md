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
| 2026-11-01 | Plan approved, with a prebuilt image in GitHub's registry instead of a slimmer local image; findings 1-7 built and tested |
| 2026-11-02 | A panel of six agents reviewed the branch; every finding that stood was fixed (see "Review panel" below) |

## Finding by finding

### 1. The message: the page opened where nothing lines up (suzhao)

**Finding.** The page opened at cycle 0 on `auipc sp,0x1`, start-up code with
no C line, so the first screen showed the one place where the layers do not
line up.

**What changed.** The backend now chooses the opening cycle
(`views.start_cycle`, served by the new `GET /api/start`). Nothing in the rule
is specific to `sum.c`: the first time the program loops back (a branch or
plain jump to a lower address in the same function, both cycles on C lines;
calls and returns do not count), else the first cycle on a C line, else cycle
0. For `sum.c` that is cycle 11, the first
`add a0,a0,a5` (`sum += i`): the C line, the instruction, its fields and the
ALU (0x0 + 0x1 = 0x1) all light up together. A cycle named in the URL still
wins.

**Tests.** Four new tests:
- `sum.c` opens on cycle 11 at `add a0,a0,a5`, C line 4.
- The rule's answer is the cycle after the loop's `bge` is first taken
  (found by hand from the listing).
- Made-up runs: a loop, calls and returns that are not loops, a missing C
  line on either side of the jump, and both fallbacks, each with its reason.
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
- **Speed.** All five plants take about 30 seconds (26 s measured), so CI
  runs it on every pull request, on both architectures.
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
  shifting in 0s like `srl`. `sum.c` never runs an `sra` instruction, but the
  shifter computes `y_sra` every cycle, so the wrong value is in the rebuilt
  trace (cycle 55: 0x80000020 >> 16 gives 0x00008000, not 0xffff8000).
  Nothing notices: Spike compares only pc, instruction and register writes,
  and the gate level and the RTL agree on the wrong design. `make regression`
  checks that this stays true, and that the plant really changed the rebuilt
  artifacts, so the blind spot stays written down until M5 brings programs
  that run every instruction.
- **The tripwire** is a0 = 55, checked two independent ways: Spike's exit
  code, and the core's own halt store in the gate-level trace (in
  `test_m2_trace.py`, and in the smoke check through the API).

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

**Finding.** On Windows, git's line-ending conversion should make the
byte-for-byte artifact tests fail although nothing changed. This was Logan's
prediction, and a precaution: in his own run all 90 tests passed.

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
line if it has no loop. Function calls and returns are not mistaken for
loops (the review panel caught that the first version did).

## Review panel

After findings 1-7, six agents reviewed the branch (`.claude/agents/`), each in
its own context with only the request, the diff and the commit messages:
- five reviewers: manager, critic, domain expert, algorithms expert and test
  engineer;
- then a refuter, which checked every finding against the code and kept only
  those that stood.

Of 49 findings (many repeated across reviewers), 2 fell entirely and 5 in
part. Every one that stood is fixed below. "Seen failing" means the new check
failed on the old behaviour before the fix made it pass.

### P1. The start-here sentence named the wrong cycle (manager, critic, algorithms)

**Finding.** "It opened on cycle 11" was shown even when a link (or a reload,
since every step writes the cycle into the URL) opened another cycle. The page
check matched only the sentence's first words.

**Fixed.** The page says why only when it chose the cycle itself. The checks
are stricter:
- `check_first_screen` compares the whole sentence with the backend's
  reason, needs exactly one lit C line and one lit instruction (class names
  parsed, so `not-current` no longer counts), and fails on an error message.
- The linked-page check fails if a page opened at `#cycle=0` gives a reason.
- `test_api` checks the reason's exact words.

**Seen failing.** With the old sentence logic, smoke failed: "a page opened
from a link still says why it opened where it did".

### P2. Calls and returns counted as loops (critic, domain expert, algorithms)

**Finding.** The rule counted any backward jump between C lines. In an M5
program, a call to a function defined earlier, or a return to a caller placed
earlier, would open the page there and call it a loop. The test said to
re-derive the rule "independently" re-used the same predicate.

**Fixed.**
- The rule counts only a branch or a plain jump (`jal zero`) to a lower
  address in the same function.
- The copied test is gone. Instead, the `sum.c` start is found from the
  listing (the cycle after the loop's `bge` is first taken).
- Made-up runs cover:
  - a call and a return, each to a lower address;
  - a missing C line on either side of the jump (the guards were untested);
  - a real "no loop" case (the old one contained a loop);
  - every reason, word for word.
- A pc that Spike ran but the listing lacks is now a 500 naming the cycle,
  not a 404 "unknown program".

**Seen failing.** With the old predicate restored,
`test_calls_and_returns_are_not_loops` failed ("the first time the program
loops back" instead of "the first cycle that runs a line of C").

### P3. The `sra` blind spot had the wrong reason, and the tests stage could not fail (critic, domain expert, test engineer)

**Finding.** `sum.c` does produce a wrong `y_sra` (cycle 55, `addi
t0,t0,48`: 0x80000020 >> 16), and the committed-trace test would catch the
bare edit. Inside `make regression`, the copy's artifacts are rebuilt first,
so that test compares the copy with itself. No plant was caught at `tests`,
and a blind spot passed even if the edit changed nothing.

**Fixed.**
- The answer key, README and section 4 above give the real reason: no check
  compares that net with a model independent of the RTL.
- The harness says why the artifacts are rebuilt first: it asks what catches
  a defect once they are rebuilt.
- A new plant, `start_one_cycle_late` (backend), is caught at `tests` by
  `test_the_page_opens_on_the_first_sum_line`. The key's test now requires
  every stage.
- A blind spot must show that its rebuilt design artifacts changed (`sra`:
  netlist, gate counts and trace).

**Seen failing.** The `sra` plant with a comment-only edit: "FAIL ... no
artifact changed, so the plant never reached the design".

### P4. The harness's own judgement was untested, and it was fragile (test engineer, critic, algorithms)

**Fixed.**
- `make test` now checks how an outcome is judged: right stage with the wrong
  message, wrong stage, not caught, and a blind spot that changed nothing or
  was caught. It also checks `apply` on text found 0 or 2 times.
- The copy's server writes to `server.log`, which is shown when its stage
  fails. Before, the output was a pipe nobody read.
- The harness stops waiting as soon as the server dies.
- A stage that cannot run counts as failing there, and the other plants still
  run.
- Clearing an old copy is no longer allowed to fail silently. While
  verifying, `rmtree(..., ignore_errors=True)` left a half-deleted copy, with
  macOS conflict copies ("build 2") that look like iCloud syncing this
  folder. The run then crashed one step later with a misleading error.

### P5. Wrong or loose claims (domain expert, critic, manager)

**Fixed.**
- **`bge_as_blt`:** the loop exits *before* its first pass (bge 10, 1 falls
  through), not after one.
- **The tripwire** has two independent checks, not three. Smoke now reads
  the core's own halt store, `(55 << 1) | 1` on `dwdata`, through the API
  (seen failing when expecting 54). It no longer just reads Spike's value a
  second time.
- **Run time:** measured at 24-26 s for five plants. It was "about 15 s" in
  two places and "minutes" in a third.
- **Windows:** worded as Logan wrote it: a predicted failure and a
  precaution; his run passed.
- **`make pull`:** the README says an image exists only once CI has
  published one. A tag means "built from the same `docker/` files", not
  identical bytes: rebuilding the artifacts showed `toolchain.json` recording
  Python 3.14.10, where the committed one said 3.14.8. The base image had
  moved, so it is now committed as rebuilt, and every base image (Python,
  Node, uv) is pinned by digest. `make base-digests` prints the current
  digests for the next upgrade.
- **The weekly from-scratch build** was not requested. It is kept and
  explained in the README: once CI pulls, nothing else would notice drift in
  the package archives.

### P6. Smaller items (critic, test engineer)

**Fixed.**
- **Empty fingerprint:** `make build`, `pull` and `publish` stop if `docker/`
  cannot be fingerprinted. Before, an empty tag matched a missing image and
  the build was skipped. Seen failing with an empty tag and with a missing
  input.
- **Tag format:** the tag hashes each file's hash, so no two different file
  sets can concatenate alike.
- **`tests/test_image.py`** fails if the Dockerfile copies a file from
  `docker/` that the fingerprint leaves out. Seen failing with `uv.lock`
  removed from `IMAGE_INPUTS`.
- **The pull failure message** points to docker's own reason, instead of
  calling every failure "no matching image".

**Fell (not changed).**
- Smoke crashing on a broken `/api/start`: it still exits non-zero, so it
  fails.
- Putting `make regression` into `make verify`: it runs in CI on every pull
  request, as approved.

## Verification

- `make verify` is green: lint, 123 tests, and the smoke check ("5 + 3 =
  0x00000008 on the gates, a0 = 55 in Spike and in the core's halt store, ...
  opens on cycle 11 with its C line lit").
- `make regression`: 5 of 5 plants behave as the answer key says, twice in a
  row, 24 s each.

## Not verified

- **The registry path end to end.** The publish job runs only on main, so the
  first image appears after this branch is merged. After that, the package
  must be set to Public once in its GitHub settings before anyone can pull it
  without logging in. Until then, `make pull` fails with the message above,
  and CI builds from scratch.
- **The CI workflow changes** run for the first time on this pull request.
- **The harness's new failure paths** (a server that dies at start-up, a
  stage that cannot run) were reasoned about, not planted.
- **A newcomer seeing the new first screen.** That is the real test of
  findings 1 and 2. I checked the screenshot myself.
