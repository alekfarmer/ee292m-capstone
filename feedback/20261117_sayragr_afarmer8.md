# Peer review, safety nets: where does the capstone stand, what does the agent know, and what catches a wrong result?

Course: Stanford University, EE292M, AI-Augmented R&D: Foundations and Practice, Fall 2026.
Form: ee292m_round6. Capstone review: yes. Written 2026-11-18 05:52 UTC by feedback_helper 147bfa0.

## Reviewer information

- SUNet ID: sayragr
- First name: Sayra
- Last name: Gorgani

## Reviewee information

- SUNet ID: afarmer8
- First name: Alek
- Last name: Farmer
- Repository: https://github.com/alekfarmer/ee292m-capstone
- Reviewed commit: 0fa40d7 on main

## Environment

- date: Tue Nov 17 22:52:12 MST 2026
- whoami: sayragorgani
- uname -a: Darwin Sayras-MacBook-Pro.local 27.0.0 Darwin Kernel Version 27.0.0: Tue Aug 11 21:02:59 PDT 2026; root:xnu-13432.1.9~1/RELEASE_ARM64_T8142 arm64
- repo path: ../ee292m-capstone

## Checklist

Score: 5 of 5

### 1. We have gone through the capstone check-in, docs/check-in.md, together, against the capstone plan: what works, what failed, what is cut, and one part to throw away and one to keep.

Verified: yes

What works, what failed, what is cut, and what the plan still claims:

What worked: Full tests are passed

What failed:
O1 folded the loop away;
the optimizer's gates were unreadable;
Yosys deleted the whole core until the memories were marked to keep;
planted bugs were reverted by hand, so they protected nothing afterwards;
typed C could read server files through #include;
a piped test command hid failing exit codes;
the message when Docker isn't running was misleading.

What got cut: -01, Verilator, phone-width and screen-reader support.

What it claims: 
- every displayed bit of the two examples is verified,
- typed programs pass the build checks but not the per-bit check,
- all 37 instructions run, but not every case of each.

### 2. We have gone through what changed in the capstone's CLAUDE.md this week together (git log -p CLAUDE.md), and why: each line added is something the agent could not have found by reading the code, and each line cut has a reason.

Verified: yes

A line added and why it is needed, and a line cut and why:

Claude.md is still one line code with @Agents.md.

### 3. We have discussed which skill the author used this week and why; or, if none was used, why not, and which repeated procedure should become a skill.

Verified: yes

The skill and why it ran; or why none, and which skill to write:

He did not use any skills. A potential option: Every fix in the check-in follows the same routine. Alek plants the defect in the answer key, confirms the right check catches it, then fixes it. A skill would keep the answer key and the README's planted-bug table in step.

### 4. We have named the safety nets of this capstone: the layers that would catch a wrong result (tests, a check against a known answer, a person's review, ...), one failure that would slip past all of them, and where the copies of the code and data are, one of them offline.

Verified: yes

The layers, the failure that slips past them, and where the copies are:

The layers that would catch a wrong result:

- The build-time cross-check. A trace is written only if three things agree in every cycle: the gate-level simulation, the design source in Icarus, and the Spike reference.
- A known answer. sum.c must leave a0 = 55. That's confirmed two independent ways: by Spike's exit code and by the core's own halt store.
- Tests. make test runs 220 tests. They include encoding rows against known values and checks that committed results are up to date.

A faliure that would slip past them: The decoders have no independent model. Spike only checks the instructions a program actually runs, with the values it runs them on. So a decoder mistake that no example program triggers would pass every layer. Alek names one in the check-in: an unknown opcode treated as a memory write.

Where the copies are
Online: Github repo
Local copy on Alek's laptop
Unsure if there is an offline copy.

### 5. We have discussed at least one suggestion I made on how this capstone could be improved.

Verified: yes

State the suggestion and what was decided:

The only thing I found unintuitive is that when I first open the website it starts from cycle 11. It would be more clear if it starts from cycle 1.

## Attestation

Completed: 5 of 5 checklist items.

All of my answers are true and accurate to the best of my understanding and ability, and I will upload this feedback to the reviewee's repository and verify that it was uploaded.

Signed: Sayra Gorgani
