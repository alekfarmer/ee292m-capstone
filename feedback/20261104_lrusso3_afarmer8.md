# Peer review, systems: where does the time go, and where does everything run?

Course: Stanford University, EE292M, AI-Augmented R&D: Foundations and Practice, Fall 2026.
Form: ee292m_round5. Capstone review: yes. Written 2026-11-05 07:19 UTC by feedback_helper 147bfa0.

## Reviewer information

- SUNet ID: lrusso3
- First name: Logan
- Last name: Russo

## Reviewee information

- SUNet ID: afarmer8
- First name: Alek
- Last name: Farmer
- Repository: https://github.com/alekfarmer/ee292m-capstone
- Reviewed commit: 1577645 on main

## Environment

- date: Wed Nov  4 23:19:05 PST 2026
- whoami: logan
- uname -a: MINGW64_NT-10.0-26300 DESKTOP-GTBBE2O 3.6.10-710e5275.x86_64 2026-07-28 09:32 UTC x86_64 Msys
- repo path: ../ee292m-capstone

## Checklist

Score: 5 of 5

### 1. We have looked at a profile of the capstone's slowest part, and at one change measured before and after that changed no answer.

Verified: yes

Where the time goes, the change, and the ratio:

(Per the README) CI got faster by downloading the prebuilt image instead of building it!

### 2. The README has a drawing of the capstone as a system, and from it I can say where each part runs and how code and data reach it.

Verified: yes

The machines or containers, and how code and data arrive:

Yes. The README has a few useful diagrams about the architecture of the project. It could benefit from another diagram about the repository structure, but the required level of information is definitely there!

### 3. We have named the original copy of the data, and what in the project cannot be rebuilt by a script, and where that is backed up.

Verified: yes

The original, what cannot be rebuilt, and where its copy is:

Yep! This is detailed in the README and (from my naive understanding) is also all available through GitHub history.

### 4. We have discussed each boundary in the system (between front end and backend, data and database, or services) and whether it is real.

Verified: yes

The boundaries, and which one is not real yet:

Yes. This is one of the more detailed diagrams available in the README.

### 5. We have discussed at least one suggestion I made on how this capstone could be improved.

Verified: yes

State the suggestion and what was decided:

Visual glitch: the C Source text runs outside the box when I view it both in Chrome and VS Code, specifically the line "return sum;   // expected: 55 in a0". It clips the boundary.
I'm still having the issue with the line endings :/ but I think that it might have just been because my cached files didn't have the fix. Asking Claude to get the repository running was quite easy and didn't require code editing. I can double check this.
Otherwise, the repo looks amazing! I took every route offered in the visualization and saw no (visual) errors. I can't speak to the accuracy, though, since I'm pretty far out of my wheelhouse here.

## Attestation

Completed: 5 of 5 checklist items.

All of my answers are true and accurate to the best of my understanding and ability, and I will upload this feedback to the reviewee's repository and verify that it was uploaded.

Signed: Logan Russo
