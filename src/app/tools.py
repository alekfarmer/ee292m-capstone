"""The one way the code starts external programs: no shell, a timeout, clear errors.

gcc, binutils, Spike, Yosys, Icarus and Chromium are all started from here
(:func:`run_tool` to run to completion, :class:`ToolStream` to read output as
it comes); tests/test_architecture.py fails if another module does it itself.
"""

import os
import subprocess
import threading
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

from app.errors import ToolError

DEFAULT_TIMEOUT_S = 120


def run_tool(
    args: Sequence[str | Path],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run ``args`` (never through a shell) and return the completed process.

    ``env`` adds to (or overrides) this process's environment.

    Raises:
        ToolError: the tool is missing, timed out, or (if ``check``) exited non-zero.
    """
    argv = [str(a) for a in args]
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, no shell
            argv,
            cwd=cwd,
            env=_environment(env),
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


def _environment(extra: Mapping[str, str] | None) -> dict[str, str] | None:
    return None if extra is None else {**os.environ, **extra}


class ToolStream:
    """A running tool whose stderr is read line by line, as it is written.

    For tools that run until told to stop (Spike keeps logging until it sees
    the halt). Use as a context manager: leaving it kills the tool if it is
    still running. A watchdog kills it after ``timeout`` seconds regardless.
    """

    def __init__(
        self,
        args: Sequence[str | Path],
        *,
        timeout: float,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        """Start ``args`` (never through a shell); ``env`` adds to this environment.

        Raises:
            ToolError: the tool is missing.
        """
        self.argv = [str(a) for a in args]
        try:
            self._proc = subprocess.Popen(  # noqa: S603 - argv list, no shell
                self.argv,
                cwd=cwd,
                env=_environment(env),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ToolError(f"tool not found: {self.argv[0]} (is the image built?)") from exc
        self._watchdog = threading.Timer(timeout, self._proc.kill)
        self._watchdog.start()

    def __enter__(self) -> ToolStream:
        """Return the stream."""
        return self

    def __exit__(self, *_: object) -> None:
        """Stop the watchdog, and the tool if it is still running."""
        self._watchdog.cancel()
        self.stop()

    def lines(self) -> Iterator[str]:
        """The tool's stderr, one line at a time, until it exits."""
        if self._proc.stderr is None:
            raise ToolError(f"{self.argv[0]}: no stderr to read")
        # A plain loop, not `yield from`: closing this generator early (the
        # caller stops reading) must not close the pipe, or the tool dies of
        # SIGPIPE instead of exiting with its own status.
        for line in self._proc.stderr:  # noqa: UP028
            yield line

    def stop(self) -> None:
        """Kill the tool (if running) and wait for it."""
        if self._proc.poll() is None:
            self._proc.kill()
        self._proc.wait()

    def finish(self, timeout: float) -> int:
        """Let the tool exit on its own (draining its output) and return its exit code.

        Raises:
            ToolError: it did not exit within ``timeout`` seconds.
        """
        try:
            self._proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            self.stop()
            raise ToolError(f"{Path(self.argv[0]).name} did not exit") from exc
        return self._proc.returncode
