# Peer review, code: is the message clear, and the structure sound?

Course: Stanford University, EE292M, AI-Augmented R&D: Foundations and Practice, Fall 2026.
Form: ee292m_round3. Capstone review: yes. Written 2026-10-21 04:55 UTC by feedback_helper 147bfa0.

## Reviewer information

- SUNet ID: suzhao
- First name: su
- Last name: zhao

## Reviewee information

- SUNet ID: afarmer8
- First name: Alek
- Last name: Farmer
- Repository: https://github.com/alekfarmer/ee292m-capstone
- Reviewed commit: 43c97e1 on m3-views

## Environment

- date: Tue Oct 20 21:55:00 PDT 2026
- whoami: suzhao
- uname -a: Darwin DN51ssav.SUNet 27.0.0 Darwin Kernel Version 27.0.0: Tue Aug 11 21:05:48 PDT 2026; root:xnu-13432.1.9~1/RELEASE_ARM64_T6041 arm64
- repo path: ../ee292m-capstone

## Checklist

Score: 5 of 5

### 1. The author walked me through the repository, and I can say what the project is for, and for whom.

Verified: yes

In one sentence, what the project is for, and for whom:

C to Gates follows one C program (sum 1 to 10) down through assembly, machine code, the datapath and the gates, cycle by cycle, for students who want to see the whole stack from software to hardware.

### 2. We have read the opening of README.md together, and it states that message to a reader outside the field.

Verified: yes

Summarize the discussion:

The opening says clearly what the project does. Who it is for ("Students interested in the whole stack from SW to HW") is only at README line 142, after the quick start and a long table of artifacts. Suggested moving the audience line and the comparison with godbolt / Ripes / Logisim to the top.

### 3. We have discussed how the code is organized: modules with one job each, and one pipeline that all the data passes through, and I understood both.

Verified: yes

Where each step lives, and the path the data takes:

Offline (make artifacts): software.py (gcc, objdump, Spike) -> program.json, sum.hex, golden.json; hardware.py (Yosys) -> netlist.json; simulate.py -> trace.json, written only when gate level, RTL and Spike agree. Serving: api.py -> pipeline.get_* -> views.py -> the page, which only draws. One pipeline: the RTL run only checks the gate-level one. Definitions have one home (paths.py, errors.py, tools.run_tool).

### 4. We have discussed the design patterns and interfaces this code uses, and where.

Verified: yes

The patterns and interfaces, and where:

One core, two adapters: api.py and cli.py both call only pipeline.py (a facade over software, hardware, simulate, views). External tools wrapped once in tools.run_tool. Typed contracts in models.py (pydantic). Precompute, then look up. In the page, one state and one show(cycle, view) refresh every pane, with a request counter that drops stale responses.

### 5. We have discussed at least one suggestion I made on how this code could be improved.

Verified: yes

State the suggestion and what was decided:

Take the one-program assumption out of the artifact names before M5: pipeline.py fixes program.json, golden.json and trace.json (lines 41-44), while the hex is already named after its program. Per-program folders, or a program name passed to get_*. Written review: https://github.com/alekfarmer/ee292m-capstone/pull/3. Decided (Alek, by email 20 Oct): he will implement it, so the code is not tied to one program, and will also move the audience line to the top of the README.

## Attestation

Completed: 5 of 5 checklist items.

All of my answers are true and accurate to the best of my understanding and ability, and I will upload this feedback to the reviewee's repository and verify that it was uploaded.

Signed: su zhao
