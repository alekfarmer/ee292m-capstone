"""Run external tools without a shell, with a timeout and clear errors."""

import subprocess
from collections.abc import Sequence
from pathlib import Path

from app.errors import ToolError

DEFAULT_TIMEOUT_S = 120


def run_tool(
    args: Sequence[str | Path],
    *,
    cwd: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run ``args`` (never through a shell) and return the completed process.

    Raises:
        ToolError: the tool is missing, timed out, or (if ``check``) exited non-zero.
    """
    argv = [str(a) for a in args]
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, no shell
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ToolError(f"tool not found: {argv[0]} (is the image built?)") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"{argv[0]} timed out after {timeout:g} s") from exc
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise ToolError(f"{Path(argv[0]).name} failed (exit {proc.returncode}): {detail}")
    return proc
