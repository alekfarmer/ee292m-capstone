# Every command the project needs runs through this file, inside the
# development container. `make help` lists the targets.

# Recipes are plain POSIX sh, so they run under make's default shell on
# Linux and macOS, and under Git Bash's sh on Windows (see the README).
.DEFAULT_GOAL := help

-include .env
export

# Name the compose project after the repository directory (lowercased,
# anything unusual replaced) so two projects never share containers.
COMPOSE_PROJECT_NAME := $(shell basename "$(CURDIR)" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/-/g')

# The container runs as you, so files it writes into the repository are yours.
# Windows has no such ids (Git Bash invents large ones, and Docker Desktop
# ignores ownership on shared folders), so use an ordinary user id there.
HOST_OS := $(shell uname -s)
ifneq ($(filter Linux Darwin,$(HOST_OS)),)
HOST_UID := $(shell id -u)
HOST_GID := $(shell id -g)
else
HOST_UID := 1000
HOST_GID := 1000
endif
export COMPOSE_PROJECT_NAME HOST_UID HOST_GID

COMPOSE := docker compose -f docker/compose.yaml
RUN     := $(COMPOSE) run --rm --no-deps app
TOOLS   := $(COMPOSE) --profile tools

# Extra arguments for pytest, e.g. `make test ARGS="-k adder"`.
ARGS ?=

LOCK_HINT := A manifest and its lock may disagree. After changing docker/pyproject.toml \
or docker/package.json, run 'make lock' and commit each manifest with its lock.

.PHONY: help build up down verify clean test lint fmt smoke logs shell lock artifacts synth-log preview screenshot

help: ## List the targets
	@echo "Everyday:"
	@echo "  build      Build the image (all tools, pinned)"
	@echo "  up / down  Start / stop the app on http://127.0.0.1:$${APP_PORT:-8000}"
	@echo "  verify     Lint, test and smoke: the gate"
	@echo "  clean      Remove this project's containers, images and generated files"
	@echo "While developing:"
	@echo "  artifacts  Regenerate everything in backend/artifacts/ (M0-M2, every program)"
	@echo "  preview    Write the adder drawings to backend/build/preview/*.svg"
	@echo "  screenshot Start the app, save page screenshots to backend/build/screenshots/, stop"
	@echo "  synth-log  Run synthesis alone, full Yosys log in backend/build/synth.log"
	@echo "  test       Run the tests (ARGS=... passes options to pytest)"
	@echo "  lint       Check the code, changing nothing"
	@echo "  fmt        Rewrite the code into the standard format"
	@echo "  smoke      Start the app, check a real API result, stop it"
	@echo "  logs       Follow the app's output"
	@echo "  shell      Open a shell inside the container"
	@echo "Only when dependencies change:"
	@echo "  lock       Record exact versions in docker/uv.lock and docker/package-lock.json"

build: ## Build the image
	@$(COMPOSE) build app || { echo; echo "$(LOCK_HINT)"; exit 1; }

up: ## Start the app
	$(COMPOSE) up -d --wait app
	@echo "App running on http://127.0.0.1:$${APP_PORT:-8000}"

down: ## Stop the app
	$(COMPOSE) down

verify: build lint test smoke ## The gate
	@echo "verify: all green"

clean: ## Back to a fresh clone (keeps .env and committed artifacts)
	$(TOOLS) down --rmi all --volumes --remove-orphans
	rm -rf backend/build .pytest_cache .ruff_cache .mypy_cache
	find src tests -name __pycache__ -type d -prune -exec rm -rf {} +

artifacts: ## Regenerate backend/artifacts/
	$(RUN) python -m app.cli artifacts

preview: ## Write the adder SVGs for viewing outside the app
	$(RUN) python -m app.cli preview

screenshot: ## Screenshots of the running page (headless Chromium in the container)
	$(COMPOSE) up -d --wait app
	@$(COMPOSE) exec -T app python -m app.pagecheck screenshot; status=$$?; $(COMPOSE) down; exit $$status

synth-log: ## Synthesis with the full Yosys log, for debugging
	@mkdir -p backend/build
	$(RUN) yosys -l backend/build/synth.log -p "script backend/rtl/synth.ys; write_json backend/build/netlist.json" > /dev/null
	@echo "log: backend/build/synth.log"

test: ## Run the tests
	$(RUN) pytest $(ARGS)

lint: ## Check the code
	$(RUN) sh -c 'ruff check src tests && ruff format --check src tests && mypy src tests'

fmt: ## Format the code
	$(RUN) sh -c 'ruff format src tests && ruff check --fix src tests'

smoke: ## Start the app, check a real result, stop it
	$(COMPOSE) up -d --wait app
	@$(COMPOSE) exec -T app python -m app.smoke; status=$$?; $(COMPOSE) down; exit $$status

logs: ## Follow the app's output
	$(COMPOSE) logs -f app

shell: ## Shell inside the container
	$(RUN) bash

lock: ## Record exact dependency versions
	$(TOOLS) run --rm --build uv-tool uv lock
	$(TOOLS) run --rm --build node-tool npm install --package-lock-only --ignore-scripts --no-audit --no-fund
