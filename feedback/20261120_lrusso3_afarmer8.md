# Peer review, safety nets: where does the capstone stand, what does the agent know, and what catches a wrong result?

Course: Stanford University, EE292M, AI-Augmented R&D: Foundations and Practice, Fall 2026.
Form: ee292m_round6. Capstone review: yes. Written 2026-11-21 01:32 UTC by feedback_helper 147bfa0.

## Reviewer information

- SUNet ID: lrusso3
- First name: Logan
- Last name: Russo

## Reviewee information

- SUNet ID: afarmer8
- First name: Alek
- Last name: Farmer
- Repository: https://github.com/alekfarmer/ee292m-capstone
- Reviewed commit: 0fa40d7 on main

## Environment

- date: Fri Nov 20 17:32:47 PST 2026
- whoami: logan
- uname -a: MINGW64_NT-10.0-26300 DESKTOP-GTBBE2O 3.6.10-710e5275.x86_64 2026-07-28 09:32 UTC x86_64 Msys
- repo path: ../ee292m-capstone

## Checklist

Score: 5 of 5

### 1. We have gone through the capstone check-in, docs/check-in.md, together, against the capstone plan: what works, what failed, what is cut, and one part to throw away and one to keep.

Verified: yes

What works, what failed, what is cut, and what the plan still claims:

Yes, all milestones are added and work! For the cuts, Verilator, extra RISC-V features and new features before the draft were removed.

### 2. We have gone through what changed in the capstone's CLAUDE.md this week together (git log -p CLAUDE.md), and why: each line added is something the agent could not have found by reading the code, and each line cut has a reason.

Verified: yes

A line added and why it is needed, and a line cut and why:

While CLAUDE nor AGENTS have changed directly, all necessary information has been tracked through very careful and detailed documentation, particularly in the README with all the feature changes and feedback responses.

### 3. We have discussed which skill the author used this week and why; or, if none was used, why not, and which repeated procedure should become a skill.

Verified: yes

The skill and why it ran; or why none, and which skill to write:

No skills were needed this week! The "close a blind spot" procedure could become a skill. The recent weeks have been more focused on documentation and refinement.

### 4. We have named the safety nets of this capstone: the layers that would catch a wrong result (tests, a check against a known answer, a person's review, ...), one failure that would slip past all of them, and where the copies of the code and data are, one of them offline.

Verified: yes

The layers, the failure that slips past them, and where the copies are:

The safety nets are pytest, the a0 = 55 known answer, the gate/RTL/Spike check on every cycle, the spot-check, the browser smoke check, the planted defects, CI and peer review!

### 5. We have discussed at least one suggestion I made on how this capstone could be improved.

Verified: yes

State the suggestion and what was decided:

It might be nice to quote $(MAKE) so that folks such as myself don't have to flag MAKE=make before running the repository (which hasn't been an issue until now... not sure why), but otherwise this repository is coming into very nice shape. This is incredibly helpful and genuinely fun to play with!!

## Attestation

Completed: 5 of 5 checklist items.

All of my answers are true and accurate to the best of my understanding and ability, and I will upload this feedback to the reviewee's repository and verify that it was uploaded.

Signed: Logan Russo
