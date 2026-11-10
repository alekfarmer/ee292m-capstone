"""The Makefile's image step, run for real with a stand-in ``docker`` on the path.

Every container target first runs ``make image``. When Docker itself is not
running, that step used to say no image was published, start a 15-25 minute
build, and then blame the manifests and their locks (found 2026-11-10).
"""

import os
from pathlib import Path

import pytest

from app.paths import REPO_ROOT
from app.tools import run_tool

# Answers like the real CLI with no daemon, and records every call it gets.
STOPPED_DOCKER = """#!/bin/sh
echo "$*" >> "$DOCKER_CALLS"
echo "Cannot connect to the Docker daemon at unix:///var/run/docker.sock." >&2
exit 1
"""


@pytest.fixture
def stopped_docker(tmp_path: Path) -> tuple[dict[str, str], Path]:
    """An environment whose ``docker`` behaves as if the daemon were stopped."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "docker"
    stub.write_text(STOPPED_DOCKER)
    stub.chmod(0o755)
    calls = tmp_path / "calls"
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "DOCKER_CALLS": str(calls)}
    return env, calls


@pytest.mark.parametrize("target", ["image", "pull", "build"])
def test_a_stopped_docker_is_named_and_nothing_is_built(
    stopped_docker: tuple[dict[str, str], Path], target: str
) -> None:
    env, calls = stopped_docker
    # The tag is given, so the test needs no git (the image has none).
    proc = run_tool(
        ["make", "--no-print-directory", "-C", REPO_ROOT, target, "IMAGE_TAG=0123456789ab"],
        env=env,
        check=False,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode != 0, output
    assert "Docker is not running" in output, output
    assert "building it instead" not in output, output
    assert "manifest and its lock" not in output, output
    made = calls.read_text().splitlines() if calls.exists() else []
    assert made == ["info"], f"docker was asked for more than whether it runs: {made}"
