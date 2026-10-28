# Peer review, tests: can it be followed, and is it tested?

Course: Stanford University, EE292M, AI-Augmented R&D: Foundations and Practice, Fall 2026.
Form: ee292m_round4. Capstone review: yes. Written 2026-10-28 05:33 UTC by feedback_helper 147bfa0.

## Reviewer information

- SUNet ID: suzhao
- First name: su
- Last name: zhao

## Reviewee information

- SUNet ID: afarmer8
- First name: Alek
- Last name: Farmer
- Repository: https://github.com/alekfarmer/ee292m-capstone
- Reviewed commit: 558071b on feedback/20261027_suzhao_afarmer8

## Environment

- date: Tue Oct 27 22:33:37 PDT 2026
- whoami: suzhao
- uname -a: Darwin DN0a1e65cd.SUNet 27.0.0 Darwin Kernel Version 27.0.0: Tue Aug 11 21:05:48 PDT 2026; root:xnu-13432.1.9~1/RELEASE_ARM64_T6041 arm64
- repo path: ../ee292m-capstone

## Checklist

Score: 5 of 5

### 1. The author walked me through the repository, and I found the contract between backend and frontend and followed one request through the code.

Verified: yes

The request, and the files it passed through:

Stepping to a cycle on the page: src/web/app.js calls fetch on GET /api/cycle/{n} and GET /api/view/{path}. src/app/api.py passes them to pipeline.get_cycle_view() and get_module_view() (pipeline.py:363, 376), which read the committed trace and netlist and call views.py to build the view; the result goes back as typed JSON (models.py), and app.js / graph.js only lay it out and draw it. Nothing is computed live: the costly work (gcc, Spike, Yosys, simulation) runs offline in make artifacts.

### 2. We have discussed the interface, and I can say what idea its main view shows.

Verified: yes

In one sentence, what the main view shows:

One C program (sum of 1 to 10) shown at every layer at once, cycle by cycle: the C line, its assembly instruction, the machine-code fields, and the datapath with the value on every wire, down to individual gates.

### 3. We have discussed which kinds of tests the project has, and I ran them all with one command.

Verified: yes

The command, and the kinds of tests it runs:

make verify (90 passed): lint; unit and integration tests, including per-wire values checked in every cycle, cycle-to-C-line mapping against Spike, architecture tests that fail when a module reaches past its interface, and API rejections; and an end-to-end smoke check that renders the real page in headless Chromium and checks a drawn wire value (pc = 0x80000000 at cycle 0).

### 4. We have discussed at least one test that has been seen to fail on a planted defect.

Verified: yes

The defect, and the test that caught it:

Treating bge as blt in the RTL: the gate level and RTL agree with each other (same wrong design), so only the comparison with Spike catches it ("cycle 11: hardware is at pc=0x8000004c, Spike at pc=0x8000003c"). Turning the adder's XORs into ORs in the gate netlist only: caught by the gate-vs-RTL comparison. Drawing every wire as 0 in the page: caught by the rendered-page smoke check.

### 5. We have discussed at least one suggestion I made on how this code could be improved.

Verified: yes

State the suggestion and what was decided:

Open the page on a sum += i cycle and add one "start here" sentence: cycle 0 is start-up code, so for a newcomer, nothing lines up on the first screen. Alek accepted by email on 27 October and will add it. Smaller: the first build takes 15-25 minutes because Yosys and Spike are compiled from source.

## Attestation

Completed: 5 of 5 checklist items.

All of my answers are true and accurate to the best of my understanding and ability, and I will upload this feedback to the reviewee's repository and verify that it was uploaded.

Signed: su zhao
