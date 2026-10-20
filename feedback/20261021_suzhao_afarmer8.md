# Session 5a: written review of the code structure

- Reviewer: Su Zhao (suzhao)
- Reviewee: Alek Farmer (afarmer8)
- Repository: https://github.com/alekfarmer/ee292m-capstone
- Reviewed commit: `43c97e1` on `m3-views`
- Date: 21 October 2026

## Status

This is a written review. We have not discussed it yet; the suggestions are only suggestions, and what to change is up to you.

## What it does, as I understand it

One small C program (summing 1 to 10) is followed all the way down: C, assembly, machine code, the datapath and the gates, cycle by cycle. Every 0 or 1 shown on a wire comes from a gate-level simulation that was checked against the RTL and against Spike. I ran `make up` and stepped through the cycles on the page.

## 1. Messaging

The opening says clearly what the project does. Who it is for is in the README too ("Students interested in the whole stack from SW to HW"), but only at line 142, after the quick start and a long table of artifacts. A first-time reader learns *what* before *why* and *for whom*. Moving the audience line, and the comparison with godbolt / Ripes / Logisim, to the top would answer "why should I care" on the first screen.

## 2. Organization

Clear, with one job per module and one data path:

- Offline (`make artifacts`): `software.py` (gcc, objdump, Spike) writes `program.json`, `sum.hex` and `golden.json`; `hardware.py` (Yosys) writes `netlist.json`; `simulate.py` writes `trace.json` only when the gate level, the RTL and Spike agree.
- Serving: `api.py` → `pipeline.get_*` → `views.py` (builds each view from the netlist and the verified trace) → the page, which only lays out and draws.

The two simulations are not two pipelines: the page shows the gate-level one, and the RTL run only checks it. Each definition has one home (`paths.py`, `errors.py`, `tools.run_tool`). Of three likely changes, fixing one calculation (`decode.py`) and adding a view (`views.py` plus one pane) each touch one place; adding a second program does not (see the suggestion).

## 3. Design patterns and interfaces

- One core with two adapters: `api.py` and `cli.py` both call only `pipeline.py`, which acts as a facade over `software`, `hardware`, `simulate` and `views`.
- External tools are wrapped once (`tools.run_tool`: no shell, a timeout, one error type).
- Typed contracts at the API (`models.py`, pydantic; `/docs` is the contract).
- Precompute, then look up: everything costly runs offline, so "jump to cycle N" is a lookup.
- In the page, one `state` and one `show(cycle, view)` refresh every pane, with a request counter that drops stale responses. Panes never talk to each other, so no observer is needed.

## 4. Suggestion

**Take the one-program assumption out of the artifact names before M5.** `pipeline.py` fixes `PROGRAM_FILE = "program.json"`, `GOLDEN_FILE = "golden.json"` and `TRACE_FILE = "trace.json"` (lines 41–44), so a second program would overwrite the first, while the hex image is already named after its program (`f"{c_file.stem}.hex"`, line 87). Per-program folders (`artifacts/sum/trace.json`), or a program name passed to `get_*`, would make this a change in `pipeline.py` and its tests now, rather than in the API and the page later, once users enter their own C.

Smaller: the README's architecture diagram has the page "load artifacts", but it actually asks the API (`/api/cycle`, `/api/view`).

## Questions for the author to consider

- In M5, will a user's program be compiled and simulated live on the server, or also precomputed? Will `verify()` still run on it?
- `views.py` (546 lines) is the largest file. Will M4 add to it, or split it?

## What Alek decided

_To be filled in after we talk._
