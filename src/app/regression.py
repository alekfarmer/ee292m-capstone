"""``make regression``: plant each defect in the answer key, check what catches it.

Each plant runs in its own copy of the repository under
``backend/build/regression/<name>/``, so the working tree is never touched.
Run as ``python -m app.regression [name ...]`` (all plants by default).
"""

import argparse
import filecmp
import shutil
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from app.errors import ToolError
from app.paths import ARTIFACTS_DIR, BUILD_DIR, REPO_ROOT
from app.regression_key import PLANTS, STAGES, Plant, Stage
from app.tools import ToolStream, run_tool

WORK_DIR = BUILD_DIR / "regression"
PORT = 8001  # the copy's server; the app itself may be running on 8000
_SKIP = shutil.ignore_patterns(".git", "build", "__pycache__", ".*_cache")


@dataclass(frozen=True)
class Outcome:
    """What happened to one plant.

    ``failed_at`` is the first stage that failed and ``output`` its output (the
    last stage's, if none failed); ``changed`` lists the artifacts the planted
    copy rebuilt differently from the committed ones.
    """

    plant: Plant
    failed_at: Stage | None
    output: str
    changed: tuple[str, ...] = ()

    @property
    def as_expected(self) -> bool:
        """Whether the plant behaved as the answer key says."""
        if self.failed_at != self.plant.caught_at:
            return False
        if self.plant.caught_at is None:
            return bool(self.changed)  # a blind spot must still have changed the design
        return self.plant.message in self.output


def apply(plant: Plant, root: Path) -> None:
    """Make the plant's edit in the copy at ``root``.

    Raises:
        ValueError: the text to replace does not occur exactly once (the code moved on).
    """
    path = root / plant.file
    text = path.read_text()
    if text.count(plant.old) != 1:
        raise ValueError(f"{plant.name}: {plant.file} does not contain its text exactly once")
    path.write_text(text.replace(plant.old, plant.new))


# Records tool versions, not the design, so it says nothing about a plant.
_NOT_DESIGN = {"toolchain.json"}


def changed_artifacts(root: Path) -> tuple[str, ...]:
    """Design artifacts in the copy at ``root`` that differ from the committed ones."""
    copy = root / ARTIFACTS_DIR.relative_to(REPO_ROOT)
    names = sorted(
        p.relative_to(ARTIFACTS_DIR)
        for p in ARTIFACTS_DIR.rglob("*")
        if p.is_file() and p.name not in _NOT_DESIGN
    )
    return tuple(
        str(n)
        for n in names
        if not (copy / n).is_file() or not filecmp.cmp(ARTIFACTS_DIR / n, copy / n, shallow=False)
    )


def _wait_for(url: str, server: ToolStream, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not server.running():
            raise ToolError("the copy's server exited before answering")
        try:
            with urllib.request.urlopen(url, timeout=2):  # noqa: S310 - local URL
                return
        except urllib.error.URLError, ConnectionError:
            time.sleep(0.5)
    raise ToolError(f"the copy's server did not answer {url} within {timeout:g} s")


def _tail(path: Path, lines: int = 30) -> str:
    text = path.read_text(errors="replace") if path.is_file() else ""
    return "\n".join(text.strip().splitlines()[-lines:])


def run_stage(stage: Stage, root: Path) -> tuple[bool, str]:
    """Run one stage in the copy at ``root``; return (passed, its output)."""
    env = {"PYTHONPATH": str(root / "src")}
    if stage == "artifacts":
        argv = ["python", "-m", "app.cli", "artifacts"]
        proc = run_tool(argv, cwd=root, env=env, timeout=1800, check=False)
        return proc.returncode == 0, proc.stdout + proc.stderr
    if stage == "tests":
        # The key's own check fails in a planted copy by design: the text is gone.
        argv = ["pytest", "-q", "--ignore=tests/test_regression_key.py"]
        proc = run_tool(argv, cwd=root, env=env, timeout=1800, check=False)
        return proc.returncode == 0, proc.stdout + proc.stderr
    server = ["uvicorn", "app.api:app", "--host", "127.0.0.1", "--port", str(PORT)]
    log = root / "server.log"
    try:
        with ToolStream(
            [*server, "--log-level", "warning"], timeout=600, cwd=root, env=env, log=log
        ) as stream:
            _wait_for(f"http://127.0.0.1:{PORT}/api/health", stream, timeout=60)
            argv = ["python", "-m", "app.smoke", "--port", str(PORT)]
            proc = run_tool(argv, cwd=root, env=env, timeout=600, check=False)
    except ToolError as exc:
        return False, f"{exc}\nthe copy's server log ended:\n{_tail(log)}"
    output = proc.stdout + proc.stderr
    if proc.returncode != 0 and _tail(log):
        output += f"\nthe copy's server log ended:\n{_tail(log)}"
    return proc.returncode == 0, output


def run_plant(plant: Plant) -> Outcome:
    """Plant the defect in a fresh copy and run the stages until one fails."""
    root = WORK_DIR / plant.name
    if root.exists():
        shutil.rmtree(root)  # loud: a copy that cannot be cleared must stop the run
    shutil.copytree(REPO_ROOT, root, ignore=_SKIP)
    apply(plant, root)
    output = ""
    for stage in STAGES:
        try:
            passed, output = run_stage(stage, root)
        except ToolError as exc:  # a stage that cannot even run counts as failing there
            passed, output = False, str(exc)
        if not passed:
            return Outcome(plant, stage, output)
    return Outcome(plant, None, output, changed_artifacts(root))


def report(outcome: Outcome) -> str:
    """One plant's result, in a line or two."""
    plant = outcome.plant
    seen = f"caught at {outcome.failed_at}" if outcome.failed_at else "not caught"
    want = f"caught at {plant.caught_at}" if plant.caught_at else "not caught (blind spot)"
    status = "ok" if outcome.as_expected else "FAIL"
    line = f"regression: {status}: {plant.name}: {seen}; the key says {want}"
    if outcome.failed_at and plant.message and plant.message not in outcome.output:
        line += f', without "{plant.message}" in its output'
    if plant.caught_at is None and outcome.failed_at is None:
        line += (
            f" (rebuilt differently: {', '.join(outcome.changed)})"
            if outcome.changed
            else ", but no artifact changed, so the plant never reached the design"
        )
    if not outcome.as_expected:
        tail = "\n".join(outcome.output.strip().splitlines()[-15:])
        line += f"\n  its output ended:\n    {tail.replace(chr(10), chr(10) + '    ')}"
    return line


def main(argv: list[str] | None = None) -> int:
    """Run the named plants (all by default); return 1 unless all behave as the key says."""
    parser = argparse.ArgumentParser(prog="app.regression", description=__doc__)
    parser.add_argument(
        "names", nargs="*", help="plants to run: " + ", ".join(p.name for p in PLANTS)
    )
    args = parser.parse_args(argv)
    unknown = set(args.names) - {p.name for p in PLANTS}
    if unknown:
        parser.error(f"no such plant: {', '.join(sorted(unknown))}")
    chosen = [p for p in PLANTS if not args.names or p.name in args.names]
    results = []
    for plant in chosen:
        print(f"regression: planting {plant.name} ({plant.defect}) ...", flush=True)
        outcome = run_plant(plant)
        print(report(outcome), flush=True)
        results.append(outcome.as_expected)
    print(f"regression: {sum(results)} of {len(results)} plants behaved as the answer key says")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
