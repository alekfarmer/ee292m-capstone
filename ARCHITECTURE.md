# Architecture

How this project is put together, and why. For a new project this is the
specification to build from; afterwards it is kept true as the project
changes. The rules that apply to every task are in AGENTS.md.

## Current state

Nothing is built yet. The repository holds only its standing documents
(README.md, AGENTS.md, CLAUDE.md, PROMPT.md and this file) and a
`.gitignore`. There is no container, no Makefile and no code.

Everything else in this file is the specification to build from: the
container, the Makefile and its targets, the backend and the page. When the
first build lands, replace this section with what actually exists, and keep
it true from then on.

## Stack

- Backend: Python 3.14 (base image pinned to the minor version,
  `python:3.14-slim`, so it takes patch fixes but never a new language
  version; never `latest` or `3`) and FastAPI, with typed request and response models; `/docs` is the
  contract.
- Frontend: static HTML and JavaScript, with no build step for our own code.
  It uses whichever library suits the view (Plotly for plots, D3 for custom
  charts, three.js for 3D); the plan names it and says why.
- Everything runs in one development container, as the host user.

## Layout

```text
docker/              everything that builds the development container, and
  Dockerfile         nothing else; it is the build context
  .dockerignore
  compose.yaml
  pyproject.toml     Python dependencies; name, version,
  uv.lock            requires-python = ">=3.14,<3.15"
  package.json       frontend libraries
  package-lock.json
src/app/             the backend: api.py (routes only), pipeline.py, models.py
src/web/             the page: index.html, app.js, styles.css
tests/               pytest
docs/                decisions worth remembering, one short file each
data/                only when the project has data: raw/ is never modified,
                     processed/ is gitignored
Makefile  README.md  ARCHITECTURE.md  AGENTS.md  CLAUDE.md
.gitignore  .env.example  ruff.toml  pytest.ini
```

## Backend

- One pipeline per API endpoint, each with one entry-point function in
  `pipeline.py`. The API calls it; tests may call any function.
- `api.py` holds routes only. It also serves our page from `src/web/` and the
  frontend libraries under `/vendor/`.
- Errors reach the page as one plain message, and the page clears any earlier
  result when it shows one: a stale plot never sits beside an error.

## The container

- The Dockerfile has four stages. Two tool stages, one with uv and one with
  Node, are where `make lock` runs, so the first lock needs no lock. A third
  installs the frontend libraries from `package-lock.json`. The final image
  holds the Python dependencies from `uv.lock` and the frontend files from
  the third stage.
- The image never copies `src/`. The repository is mounted at `/work`, with
  `PYTHONPATH=/work/src`.
- Frontend libraries are installed at build time from `package-lock.json` and
  copied into the image outside `/work` (the mount would hide them). Never
  installed on the host, never committed, never loaded from a CDN.
- `compose.yaml` publishes on `127.0.0.1` and runs as the host user (its user
  and group IDs passed in by the Makefile), with `HOME` set to a writable
  directory inside the container for the tools' caches.
- The Makefile names the compose project after the repository directory
  (`COMPOSE_PROJECT_NAME`), so two projects never share containers or images.
- `.env` holds plain `KEY=value` lines, without quotes; the Makefile includes
  and exports it, because compose pointed at `docker/` would not find it.

## Makefile

`make help` (the default) lists every target in three groups.

Everyday, the only ones a user needs:

- `build`: build everything the project needs, into the image.
- `up` and `down`: start and stop the app.
- `verify`: check that it all works (lint, test, smoke). Must pass from a
  fresh clone with only Docker, Make and git installed.
- `clean`: return to the state of a fresh clone. This project's containers,
  images and generated files are removed; `data/raw/` and `.env` are kept, and
  so are the base images and build cache Docker shares with other projects.

While developing:

- `test`: run the tests. `lint`: check the code, changing nothing. `fmt`:
  rewrite the code into the standard format.
- `smoke`: start the app, check a real API result (not just a status code),
  stop it again.
- `logs` and `shell`: follow the app's output; open a shell inside the
  container.

Only when dependencies change:

- `lock`: after adding, removing or upgrading a package in
  `docker/pyproject.toml` or `docker/package.json`, record the exact versions
  in `docker/uv.lock` and `docker/package-lock.json`, and commit each manifest
  with its lock. `build` uses only what the locks record, and says so, with
  this instruction, when a manifest and its lock disagree.

Every target runs through compose (`docker compose -f docker/compose.yaml`).
