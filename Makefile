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

# The prebuilt image (`make pull`). Its tag is a fingerprint of every file the
# image is built from, so a pulled image always matches this checkout's docker/.
IMAGE_REPO ?= ghcr.io/alekfarmer/ee292m-capstone
IMAGE_INPUTS := docker/Dockerfile docker/pyproject.toml docker/uv.lock docker/package.json docker/package-lock.json
IMAGE_TAG := $(shell git hash-object $(IMAGE_INPUTS) | git hash-object --stdin | cut -c1-12)
IMAGE_MISSING := $(filter-out $(wildcard $(IMAGE_INPUTS)),$(IMAGE_INPUTS))
IMAGE := $(COMPOSE_PROJECT_NAME)-app
export IMAGE_TAG
# Stops a recipe when docker/ cannot be fingerprinted, rather than tagging with ''.
CHECK_TAG = @if [ -n "$(IMAGE_MISSING)" ] || [ -z "$(IMAGE_TAG)" ]; then \
  echo "Cannot fingerprint docker/ (missing: $(or $(IMAGE_MISSING),none); is git installed?)"; exit 1; fi

COMPOSE := docker compose -f docker/compose.yaml
RUN     := $(COMPOSE) run --rm --no-deps app
TOOLS   := $(COMPOSE) --profile tools

# Extra arguments for pytest, e.g. `make test ARGS="-k adder"`.
ARGS ?=
# Plants for `make regression`, e.g. `make regression PLANT=bge_as_blt` (default: all).
PLANT ?=
# For `make pr`: the pull request's title and a file holding its description.
TITLE ?=
BODY ?=

LOCK_HINT := A manifest and its lock may disagree. After changing docker/pyproject.toml \
or docker/package.json, run 'make lock' and commit each manifest with its lock.

.PHONY: help build up down verify clean test lint fmt smoke spot-check logs shell lock artifacts synth-log preview screenshot regression pr pr-body \
	pull publish publish-manifest base-digests

help: ## List the targets
	@echo "Everyday:"
	@echo "  pull       Download the prebuilt image for this checkout (minutes; instead of build)"
	@echo "  build      Build the image (all tools, pinned; skipped if it already matches docker/)"
	@echo "  up / down  Start / stop the app on http://127.0.0.1:$${APP_PORT:-8000}"
	@echo "  verify     Lint, test, spot-check and smoke: the gate"
	@echo "  pr         Open a pull request from this branch into main (TITLE=..., BODY=file)"
	@echo "  pr-body    Replace the description of this branch's pull request (BODY=file)"
	@echo "  clean      Remove this project's containers, images and generated files"
	@echo "While developing:"
	@echo "  artifacts  Regenerate everything in backend/artifacts/ (M0-M2, every program)"
	@echo "  preview    Write the adder drawings to backend/build/preview/*.svg"
	@echo "  screenshot Start the app, save page screenshots to backend/build/screenshots/, stop"
	@echo "  synth-log  Run synthesis alone, full Yosys log in backend/build/synth.log"
	@echo "  test       Run the tests (ARGS=... passes options to pytest)"
	@echo "  lint       Check the code, changing nothing"
	@echo "  fmt        Rewrite the code into the standard format"
	@echo "  spot-check Check every drawn bit of every view in every cycle (M4)"
	@echo "  smoke      Start the app, check a real API result, stop it"
	@echo "  regression Plant each defect in the answer key and check what catches it (PLANT=name)"
	@echo "  logs       Follow the app's output"
	@echo "  shell      Open a shell inside the container"
	@echo "Only when dependencies change:"
	@echo "  lock       Record exact versions in docker/uv.lock and docker/package-lock.json"
	@echo "  base-digests  Print the digests of the base images, to pin in docker/Dockerfile"
	@echo "CI only:"
	@echo "  publish, publish-manifest  Push the verified image to $(IMAGE_REPO)"

pull: ## Download the prebuilt image that matches docker/ (tag IMAGE_TAG)
	$(CHECK_TAG)
	@docker pull $(IMAGE_REPO):$(IMAGE_TAG) || { echo; \
	  echo "Could not pull $(IMAGE_REPO):$(IMAGE_TAG); docker's reason is above."; \
	  echo "If the image is not found, none is published for this checkout's docker/ (yet, or you changed it): run 'make build'."; \
	  exit 1; }
	docker tag $(IMAGE_REPO):$(IMAGE_TAG) $(IMAGE)

build: ## Build the image, unless the one there already matches docker/
	$(CHECK_TAG)
	@if [ "$$(docker image inspect --format '{{index .Config.Labels "ee292m.image-tag"}}' $(IMAGE) 2>/dev/null)" = "$(IMAGE_TAG)" ]; then \
	  echo "build: the image already matches docker/ ($(IMAGE_TAG))"; \
	else \
	  $(COMPOSE) build app || { echo; echo "$(LOCK_HINT)"; exit 1; }; \
	fi

up: ## Start the app
	$(COMPOSE) up -d --wait app
	@echo "App running on http://127.0.0.1:$${APP_PORT:-8000}"

down: ## Stop the app
	$(COMPOSE) down

verify: build lint test spot-check smoke ## The gate
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

regression: ## Planted defects caught as the answer key says (src/app/regression_key.py)
	$(RUN) python -m app.regression $(PLANT)

spot-check: ## Every drawn bit of every view in every cycle, and every unit against a model
	$(RUN) python -m app.spotcheck

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

# The base images the Dockerfile starts FROM, by tag; their digests are pinned there.
BASE_IMAGES := python:3.14.10-slim-trixie node:22.20.0-bookworm-slim ghcr.io/astral-sh/uv:0.9.5

base-digests: ## The multi-architecture digest of each base image (to pin in the Dockerfile)
	@for image in $(BASE_IMAGES); do \
	  echo "$$image@$$(docker buildx imagetools inspect $$image --format '{{.Manifest.Digest}}')"; \
	done

pr: ## Open a pull request from this branch into main (TITLE=..., BODY=file)
	@branch="$$(git rev-parse --abbrev-ref HEAD)"; \
	 if [ "$$branch" = main ]; then echo "pr: on main; open a PR from a feature branch" >&2; exit 1; fi; \
	 if [ -z "$(TITLE)" ] || [ ! -f "$(BODY)" ]; then echo "pr: needs TITLE=... and BODY=<file>" >&2; exit 1; fi; \
	 gh pr create --base main --head "$$branch" --title "$(TITLE)" --body-file "$(BODY)"

pr-body: ## Replace the description of this branch's open pull request (BODY=file)
	@branch="$$(git rev-parse --abbrev-ref HEAD)"; \
	 if [ "$$branch" = main ]; then echo "pr-body: on main; run it on a feature branch" >&2; exit 1; fi; \
	 if [ ! -f "$(BODY)" ]; then echo "pr-body: needs BODY=<file>" >&2; exit 1; fi; \
	 gh pr edit "$$branch" --body-file "$(BODY)"

publish: ## CI only: push this machine's verified image as IMAGE_TAG-<arch>
	$(CHECK_TAG)
	arch="$$(docker version --format '{{.Server.Arch}}')" \
	 && docker tag $(IMAGE) $(IMAGE_REPO):$(IMAGE_TAG)-$$arch \
	 && docker push $(IMAGE_REPO):$(IMAGE_TAG)-$$arch

publish-manifest: ## CI only: one name for both architectures' images
	$(CHECK_TAG)
	docker buildx imagetools create -t $(IMAGE_REPO):$(IMAGE_TAG) \
	  $(IMAGE_REPO):$(IMAGE_TAG)-amd64 $(IMAGE_REPO):$(IMAGE_TAG)-arm64
