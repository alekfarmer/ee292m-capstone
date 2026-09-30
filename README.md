# Starting point

A starting point for your own data visualization or small research project,
from **EE292M: AI-Augmented R&D: Foundations and practice** (Stanford, Fall
2026).

It holds no code. It holds the standards a coding agent builds under, so that
your first prompt can be almost entirely about your problem. The agent builds
the rest: the container, the Makefile, a Python backend and a web page.

## What is here

```text
AGENTS.md        the rules, for anyone, human or AI, working in this repository
CLAUDE.md        one line that points Claude Code to AGENTS.md
ARCHITECTURE.md  the design: the stack, the layout, the container, the Makefile
PROMPT.md        where you write your problem, before you paste it to the agent
.gitignore       what never belongs in git: .DS_Store, .env, derived data
```

Codex reads AGENTS.md directly. Claude Code reads CLAUDE.md, which imports
it. Either agent ends up under the same rules.

## Before you start

You need git and a GitHub account, Docker (Docker Desktop, or Docker Engine
with the Compose plugin), `make`, and Claude Code or Codex. Nothing else is
installed on your machine; everything your project needs lives in its
container.

On Windows, work in PowerShell and Git Bash, not in a WSL Linux terminal, and
run `make` from Git Bash.

## How to use it

1. **Make it yours.** Create a private repository on GitHub and copy these
   files into it. Make the first commit on `main` yourself, then create a
   feature branch for the agent.
2. **Write your problem in PROMPT.md.** Say what, not how: the data or the
   physics, what the page shows, the inputs and their limits. Then add the
   truths the result must satisfy (see below).
3. **Paste it to your agent.** It replies first with a plan, the files it will
   touch, its assumptions and its questions. Read the plan the way you would
   read a student's proposal. Correct it, answer the questions, then approve.
   This is the cheapest moment to change the design.
4. **Watch the build.** Refuse anything on the host. Never click "always
   allow" for docker, gh, curl, wget, pip or brew; those belong in Makefile
   targets. Keep the agent on its feature branch.
5. **Check it yourself.** Run `make clean`, then `make verify`, and see it go
   green. Look at what changed in GitHub Desktop and what is running in Docker
   Desktop, not at the agent's summary of it.
6. **Merge through a pull request** that you review. `main` changes no other
   way.

Once the project exists, rewrite this README for it: what it does, how to run
it, and what its results are fit for. AGENTS.md holds the agent to keeping it
true.

## Writing the prompt

A good prompt names the standards file and moves on. What remains is the
problem, and the lines only you could write: statements the result must
satisfy, which become tests that fail when it is wrong. Each one should catch
a bug a plot would hide. Check every one of them yourself before it goes in.

The reference example from Week 2:

```text
Follow AGENTS.md.

Build a small web app that plots the frequency response of a series RLC
low-pass, output across the capacitor:
H(f) = 1 / (1 − (2πf)²LC + j2πfRC).

The user enters R, L and C, in ohms, henries and farads. The backend returns
|H| in dB from f₀ / 1000 to 1000 f₀, at 100 points per decade, and the page
plots it on a logarithmic frequency axis. Anything that is not a finite
positive number, such as 10 or 1e-6, is rejected by the backend, and the page
shows its message.

It must satisfy, with f₀ = 1 / (2π√(LC)) and Q = (1/R)√(L/C):

- 20 log₁₀ |H(f₀)| = 20 log₁₀ Q within 0.01 dB, for circuits across the
  whole range of R from 1 mΩ to 1 MΩ, L from 1 nH to 10 H and C from 1 fF to
  10 mF
- For R = 10 Ω, L = 1 mH, C = 1 µF: 0 dB at f₀ / 1000, and a fall of 40 dB
  from 100 f₀ to 1000 f₀, both within 0.1 dB
```

If your project has a dataset, say where it lives (`data/raw/`, committed as
received and never modified) and what a few of its numbers must come out to,
computed by hand.

## Staying honest

- Results are computed by the backend and tested. The page draws them and
  computes nothing a scientist would call a result.
- A green check is a metric, not a proof. Ask of every result: what does this
  actually claim, and what would falsify it?
- You are accountable for everything you submit, whoever typed it.
