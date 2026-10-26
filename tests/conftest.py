"""Shared fixtures: build every artifact fresh, once per test session."""

from pathlib import Path

import pytest

from app import pipeline


@pytest.fixture(scope="session")
def fresh_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Run every pipeline into a temporary directory and return it."""
    root = tmp_path_factory.mktemp("fresh")
    out = root / "artifacts"
    pipeline.build_hardware_artifacts(out, root / "hw")
    pipeline.build_program_artifacts(out_dir=out, work_dir=root / "sw")
    pipeline.build_trace_artifacts(out, root / "trace")
    return out
