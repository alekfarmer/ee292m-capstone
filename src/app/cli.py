"""Command line for offline steps: ``python -m app.cli artifacts``."""

import argparse
import sys

from app import pipeline
from app.errors import PipelineError
from app.paths import BUILD_DIR, REPO_ROOT


def main(argv: list[str] | None = None) -> int:
    """Run a command; return the process exit status."""
    parser = argparse.ArgumentParser(prog="app.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("artifacts", help="regenerate everything in backend/artifacts/")
    sub.add_parser("preview", help="write each adder case's SVG to backend/build/preview/")
    args = parser.parse_args(argv)

    if args.command == "artifacts":
        try:
            pipeline.build_all()
        except PipelineError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        counts = pipeline.get_gate_counts()
        print("Gate counts (including submodules):")
        for row in counts.summary:
            print(f"  {row.total_gates:6d}  {row.label} [{row.module}]")
        for name in pipeline.list_programs():
            golden = pipeline.get_golden(program=name)
            trace = pipeline.get_trace(program=name)
            v = trace.verification
            print(
                f"{name}: Spike retired {golden.retired} instructions, "
                f"a0 = {golden.a0_at_halt}, exit code {golden.exit_code}; "
                f"trace {trace.cycles} cycles, {len(trace.signals)} signals, "
                f"gate level = RTL on {v.gate_vs_rtl_signals} signals every cycle, "
                f"{v.register_writes_checked} register writes match Spike"
            )
        for case in pipeline.list_adder_cases():
            view = pipeline.get_adder_view(case.case_id)
            print(f"Adder {view.label}: sum = {view.sum}, cout = {view.cout}")
    elif args.command == "preview":
        out = BUILD_DIR / "preview"
        out.mkdir(parents=True, exist_ok=True)
        try:
            for case in pipeline.list_adder_cases():
                path = out / f"adder_{case.case_id}.svg"
                path.write_text(pipeline.get_adder_view(case.case_id).svg)
                print(path.relative_to(REPO_ROOT))
        except PipelineError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
