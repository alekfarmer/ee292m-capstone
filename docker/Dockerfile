# syntax=docker/dockerfile:1.7
#
# The development image. Every tool the project uses is pinned here and
# installed at build time; nothing is installed while the app runs.
#
# Stages:
#   uv-tool, node-tool  where `make lock` runs (so the first lock needs no lock)
#   frontend            frontend libraries from package-lock.json
#   yosys-build         Yosys built from a release tag
#   spike-build         Spike (riscv-isa-sim) built from a pinned commit
#   final               Python deps from uv.lock + the tools above

ARG PYTHON_BASE=python:3.14-slim-trixie

# --------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:0.9.5 AS uv-bin

FROM ${PYTHON_BASE} AS uv-tool
COPY --from=uv-bin /uv /usr/local/bin/uv
WORKDIR /lock

FROM node:22.20.0-bookworm-slim AS node-tool
WORKDIR /lock

# --------------------------------------------------------------------------
FROM node-tool AS frontend
WORKDIR /frontend
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund && mkdir -p node_modules

# --------------------------------------------------------------------------
FROM ${PYTHON_BASE} AS yosys-build
ARG YOSYS_TAG=v0.68
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential cmake git ca-certificates bison flex gawk pkg-config \
      libffi-dev libfl-dev libreadline-dev tcl-dev zlib1g-dev \
 && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${YOSYS_TAG}" https://github.com/YosysHQ/yosys.git /src/yosys
WORKDIR /src/yosys
RUN git submodule update --init
RUN cmake -B build . -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/yosys \
 && cmake --build build --config Release --parallel "$(nproc)" \
 && cmake --install build --strip

# --------------------------------------------------------------------------
FROM ${PYTHON_BASE} AS spike-build
ARG SPIKE_COMMIT=f8a060b
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential git ca-certificates device-tree-compiler \
 && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/riscv-software-src/riscv-isa-sim.git /src/spike
WORKDIR /src/spike
RUN git checkout "${SPIKE_COMMIT}" \
 && mkdir build && cd build \
 && ../configure --prefix=/opt/spike \
 && make -j"$(nproc)" \
 && make install \
 && git -C /src/spike rev-parse HEAD > /opt/spike/COMMIT

# --------------------------------------------------------------------------
FROM ${PYTHON_BASE} AS final
# Debian trixie package versions are pinned exactly. iverilog's binary
# rebuild suffix differs by architecture (+b1 amd64, +b2 arm64), so it is
# pinned to the source version 12.0-2.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      gcc-riscv64-unknown-elf=14.2.0+19 \
      binutils-riscv64-unknown-elf=2.44-3+7+b1 \
      'iverilog=12.0-2*' \
      fonts-dejavu-core \
      device-tree-compiler \
      libreadline8t64 libtcl8.6 libffi8 zlib1g \
 && rm -rf /var/lib/apt/lists/*

# Headless Chromium, for the page checks in `make smoke` and `make screenshot`
# only (never used by the app). Debian ships Chromium through security updates
# that delete older builds from the archive, so it is pinned exactly through
# snapshot.debian.org, which keeps every build for good. To upgrade, pick a
# newer build and its "seen in" timestamp from
# https://snapshot.debian.org/package/chromium/ and change both ARGs.
# chromium-common is pinned too: chromium-headless-shell needs exactly the same
# version, and the live security archive would otherwise offer a newer one.
ARG CHROMIUM_VERSION=156.0.8078.47-1~deb13u1
ARG CHROMIUM_SNAPSHOT=20261022T170820Z
RUN signed_by="$(grep -m1 '^Signed-By:' /etc/apt/sources.list.d/debian.sources)" \
 && printf '%s\n' \
      'Types: deb' \
      "URIs: http://snapshot.debian.org/archive/debian-security/${CHROMIUM_SNAPSHOT}" \
      'Suites: trixie-security' \
      'Components: main' \
      'Check-Valid-Until: no' \
      "${signed_by}" \
      > /etc/apt/sources.list.d/chromium-snapshot.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      "chromium-headless-shell=${CHROMIUM_VERSION}" \
      "chromium-common=${CHROMIUM_VERSION}" \
 && rm /etc/apt/sources.list.d/chromium-snapshot.sources \
 && rm -rf /var/lib/apt/lists/*

COPY --from=uv-bin /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /opt/project
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-cache

COPY --from=yosys-build /opt/yosys /opt/yosys
COPY --from=spike-build /opt/spike /opt/spike
COPY --from=frontend /frontend/node_modules /opt/vendor

ENV PATH=/opt/venv/bin:/opt/yosys/bin:/opt/spike/bin:${PATH} \
    PYTHONPATH=/work/src \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp
WORKDIR /work
EXPOSE 8000
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
