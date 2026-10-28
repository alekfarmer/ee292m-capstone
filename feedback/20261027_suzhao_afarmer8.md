# Session 6a: review of testing and trust

- Reviewer: Su Zhao (suzhao)
- Reviewee: Alek Farmer (afarmer8)
- Repository: https://github.com/alekfarmer/ee292m-capstone
- Reviewed commit: `a92a83d` on `main` (merge of PR #5, m3-views)
- Date: 27 October 2026

## Status

This is a written review. We have not discussed it yet; the suggestions are only suggestions, and what to change is up to you.

## What I ran

`make verify` after a fresh pull: the image rebuilt (the Dockerfile changed), lint passed, **90 tests passed**, and the smoke check reported "5 + 3 = 0x00000008 on the gates, a0 = 55 in Spike, 57-cycle trace, page renders the datapath with pc = 0x80000000". Then `make up` and the page at 127.0.0.1:8000: cycle 0, then stepping with "line ▶" to cycle 29.

## 1. Is the message clear?

In the README, yes: it now opens with who it is for and a plain-terms paragraph, which answers last round's point.

On the page, not yet for someone like me. I come from chemistry, not hardware, and when the page opened I could not tell where to look. Four panels appear at once, and it opens at cycle 0 on `auipc sp,0x1`, which is start-up code: its "line" column is "–" and nothing in the C panel is highlighted, so the first thing a newcomer sees is the one place where the layers do *not* line up. See the suggestion.

## 2. Are the interfaces clear?

Yes, and they are tested. `test_architecture.py` fails when a module reaches past its one narrow interface, so the module boundaries in README and ARCHITECTURE are enforced, not only described. Every external program now starts through `tools.py`.

## 3. Are the tests clear?

Yes. The tests re-derive each check from the artifacts rather than trusting the pipeline's own checks, and the progress notes say plainly what is not verified (clicks, keys and play; only `sum.c`; only headless Chromium in light mode).

## 4. Why should I trust this?

Because there are two independent referees, and each has been shown to catch a bug the other cannot. Treating `bge` as `blt` in the RTL makes the gate level and the RTL agree with each other (both run the same wrong design), so only the comparison with Spike catches it. Turning the adder's XORs into ORs in the gate netlist only is caught by the gate-vs-RTL comparison. The smoke check also renders the real page and checks a drawn wire value, and drawing every wire as 0 was caught by it, so the frontend is tested too, not only the numbers.

## Suggestion

**Guide the first look.** The idea is already in the data; the page only needs to point at it. Two small changes:

1. **Open on a cycle of `sum += i`** (for example the `add a0,a0,a5` at 0x8000003c), not on cycle 0. Then the C line, the assembly line, the machine-code fields and the ALU all light up together on the first screen.
2. **Add one "start here" sentence** beside the hardware view, for example: "Press line ▶. The highlighted C line becomes the highlighted instruction, and in the datapath the ALU computes it: a + b = result."

Someone had to read the datapath to me before I saw what it shows. At cycle 29 (`addi a4,zero,10`, the 10 in `i <= 10`), the ALU reads a = 0x0, b = 0xa, result = 0xa, and rd2 carries 0xf, which is `sum` = 1 + 2 + 3 + 4 + 5. Following a number from C onto a wire is the best moment on the page, and one sentence would let a beginner find it alone.

Smaller:

- **The first build takes 15–25 minutes and keeps every CPU core busy** (my laptop's fans came on), because Yosys and Spike are compiled from source. That is a high bar for a classmate who wants to try it once. A prebuilt image pulled from a registry, or a "quick look" path that serves the committed artifacts without the toolchain, would make the first run take minutes.

## Questions for the author to consider

- The planted bugs (bge as blt, XOR as OR, every wire drawn as 0) were each caught and then reverted by hand. Would it be worth keeping them as an automatic check (a `make regression` that plants each one in a copy and expects the matching test to fail), so they keep protecting you after M4 and M5 change the code?
- In M5, when a user types their own C, will the page still open on a meaningful cycle, for example the first one that belongs to a C line?

## What Alek decided

(To be filled after we discuss.)
