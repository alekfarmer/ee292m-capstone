"""Each program gets its own artifacts, so a second one overwrites nothing (suzhao, PR #3)."""

import shutil
from pathlib import Path

import pytest

from app import pipeline
from app.paths import SUM_PROGRAM

# A second program in the supported subset: 3 + 2 + 1, so a0 = 6.
COUNTDOWN = """int main(void) {
    int total = 0;
    for (int n = 3; n > 0; n--)
        total += n;
    return total;
}
"""


@pytest.fixture(scope="module")
def two_programs(fresh_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """An artifact folder holding sum.c and countdown.c, built one after the other."""
    root = tmp_path_factory.mktemp("two")
    out = root / "artifacts"
    out.mkdir()
    shutil.copy(fresh_dir / pipeline.NETLIST_FILE, out / pipeline.NETLIST_FILE)
    shutil.copy(fresh_dir / pipeline.GATE_COUNTS_FILE, out / pipeline.GATE_COUNTS_FILE)
    countdown = root / "countdown.c"
    countdown.write_text(COUNTDOWN)
    for c_file in (SUM_PROGRAM, countdown):
        pipeline.build_program_artifacts(c_file, out, root / "work")
        pipeline.build_trace_artifacts(out, root / "trace", program=c_file.stem)
    return out


def test_each_program_keeps_its_own_results(two_programs: Path) -> None:
    assert pipeline.list_programs(two_programs) == ["countdown", "sum"]
    assert pipeline.get_golden(two_programs, program="sum").exit_code == 55
    assert pipeline.get_golden(two_programs, program="countdown").exit_code == 6
    assert pipeline.get_program(two_programs, program="sum").source_file == "sum.c"
    assert pipeline.get_program(two_programs, program="countdown").source_file == "countdown.c"
    sum_trace = pipeline.get_trace(two_programs, program="sum")
    countdown_trace = pipeline.get_trace(two_programs, program="countdown")
    assert sum_trace.cycles == pipeline.get_golden(two_programs, program="sum").retired
    assert countdown_trace.cycles == pipeline.get_golden(two_programs, program="countdown").retired
    assert sum_trace.cycles != countdown_trace.cycles


def test_views_follow_the_chosen_program(two_programs: Path) -> None:
    golden = pipeline.get_golden(two_programs, program="countdown")
    last = golden.retired - 1
    cv = pipeline.get_cycle_view(last, two_programs, program="countdown")
    assert cv.halt and cv.pc == golden.entries[-1].pc
    view = pipeline.get_module_view("top.rv.dp", 0, two_programs, program="countdown")
    assert view.module == "datapath"


def test_unknown_program_is_a_key_error(two_programs: Path) -> None:
    with pytest.raises(KeyError):
        pipeline.get_golden(two_programs, program="nope")
