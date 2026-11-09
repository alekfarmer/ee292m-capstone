"""Shared fixtures: build every artifact fresh, once per test session."""

from pathlib import Path

import pytest

from app import pipeline


@pytest.fixture(scope="session")
def fresh_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Run every pipeline, for every committed program, into a temporary directory."""
    root = tmp_path_factory.mktemp("fresh")
    out = root / "artifacts"
    pipeline.build_hardware_artifacts(out, root / "hw")
    for c_file in pipeline.committed_sources():
        pipeline.build_program_artifacts(c_file, out, root / "sw")
        pipeline.build_trace_artifacts(out, root / "trace", program=c_file.stem)
    return out
