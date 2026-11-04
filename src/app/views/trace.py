"""The verified gate-level trace, expanded to one snapshot per cycle."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.errors import PipelineError
from app.models import TraceArtifact


@dataclass(frozen=True)
class TraceIndex:
    """The trace expanded to one ``{signal: value}`` dict per cycle."""

    widths: dict[str, int]
    cycles: list[dict[str, int]]

    def value(self, cycle: int, signal: str) -> int:
        """The value of ``signal`` in ``cycle``."""
        try:
            return self.cycles[cycle][signal]
        except KeyError as exc:
            raise PipelineError(f"signal {signal} is not in the trace") from exc


def expand_trace(trace: TraceArtifact) -> TraceIndex:
    """Turn the change list into a full snapshot per cycle."""
    names = [s.name for s in trace.signals]
    cur = {n: int(v, 16) for n, v in zip(names, trace.initial, strict=True)}
    cycles = [dict(cur)]
    for changes in trace.changes:
        for i, v in changes:
            cur[names[i]] = int(v, 16)
        cycles.append(dict(cur))
    return TraceIndex({s.name: s.width for s in trace.signals}, cycles)


@lru_cache(maxsize=4)
def _cached_index(path: str, mtime_ns: int) -> TraceIndex:
    return expand_trace(TraceArtifact.model_validate_json(Path(path).read_text()))


def trace_index(trace_path: Path) -> TraceIndex:
    """The expanded trace, cached until the file changes."""
    return _cached_index(str(trace_path), trace_path.stat().st_mtime_ns)
