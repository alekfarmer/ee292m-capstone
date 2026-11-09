"""M5: a user's C program is built live, checked like sum.c, and served by name.

The expected results are worked out by hand from the C, not read from Spike.
"""

import threading
from pathlib import Path

import pytest

from app import pipeline
from app.errors import BuildBusyError, ProgramRejectedError

# Accepted programs: source, and a0 at the halt, worked out by hand.
ACCEPTED = {
    "fibonacci": (
        "int main(void) {\n"
        "    int a = 0, b = 1;\n"
        "    for (int i = 0; i < 12; i++) {\n"
        "        int t = a + b;\n"
        "        a = b;\n"
        "        b = t;\n"
        "    }\n"
        "    return a;\n"
        "}\n",
        144,  # fib(12)
    ),
    "array_max": (
        "int v[6] = {3, -7, 12, 5, 0, 9};\n"
        "int main(void) {\n"
        "    int m = v[0];\n"
        "    for (int i = 1; i < 6; i++)\n"
        "        if (v[i] > m)\n"
        "            m = v[i];\n"
        "    return m;\n"
        "}\n",
        12,
    ),
    "recursion": (
        "int tri(int n) {\n"
        "    if (n == 0)\n"
        "        return 0;\n"
        "    return n + tri(n - 1);\n"
        "}\n"
        "int main(void) { return tri(6); }\n",
        21,  # 6 + 5 + 4 + 3 + 2 + 1
    ),
    "shift_and_add_multiply": (
        "int mul(int a, int b) {\n"
        "    int r = 0;\n"
        "    while (b) {\n"
        "        if (b & 1)\n"
        "            r += a;\n"
        "        a <<= 1;\n"
        "        b >>= 1;\n"
        "    }\n"
        "    return r;\n"
        "}\n"
        "int main(void) { return mul(7, 6); }\n",
        42,
    ),
    "count_bits": (
        "volatile unsigned x = 0xF0F0u;\n"
        "int main(void) {\n"
        "    unsigned v = x;\n"
        "    int c = 0;\n"
        "    while (v) {\n"
        "        c += v & 1;\n"
        "        v >>= 1;\n"
        "    }\n"
        "    return c;\n"
        "}\n",
        8,
    ),
    "char_and_short": (
        "signed char c = -5;\nshort s = 300;\nint main(void) { return c + s; }\n",
        295,
    ),
}

# Rejected at the size limits, before any tool runs.
TOO_BIG = {
    "too_many_bytes": (
        "int main(void) { return 0; }\n" + "//" + "x" * pipeline.MAX_SOURCE_BYTES,
        "bytes",
    ),
    "too_many_lines": (
        "int main(void) { return 0; }\n" + "\n" * pipeline.MAX_SOURCE_LINES,
        "lines",
    ),
    "control_character": ("int main(void) { return 0; }\x00\n", "control character"),
    "empty": ("  \n\n", "empty"),
}

# Rejected by the same checks as a committed program.
OUTSIDE_SUBSET = {
    "float": ("int main(void) { float x = 2; return (int)x; }\n", "floating-point"),
    "no_halt": ("int g;\nint main(void) { while (1) { g = g + 1; } }\n", "did not halt within 500"),
    "include": ('#include "/work/.env"\nint main(void) { return 0; }\n', "'#'"),
}


@pytest.fixture
def user_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """User programs go to a temporary folder for each test."""
    folder = tmp_path / "user"
    monkeypatch.setattr(pipeline, "USER_DIR", folder)
    return folder


@pytest.mark.parametrize("name", sorted(ACCEPTED))
def test_an_accepted_program_runs_and_is_served_by_name(
    name: str, fresh_dir: Path, user_dir: Path
) -> None:
    source, a0 = ACCEPTED[name]
    built = pipeline.build_user_program(source, fresh_dir)
    assert not built.cached
    golden = pipeline.get_golden(fresh_dir, program=built.program)
    assert golden.a0_at_halt == f"0x{a0:08x}"
    # Everything the page asks for is served, as for sum.c.
    listing = pipeline.get_program(fresh_dir, program=built.program)
    assert listing.source_file == pipeline.USER_SOURCE_FILE
    assert "".join(f"{line.text}\n" for line in listing.c_lines) == source
    trace = pipeline.get_trace(fresh_dir, program=built.program)
    assert trace.cycles == golden.retired
    start = pipeline.get_start_cycle(fresh_dir, program=built.program)
    pipeline.get_cycle_view(start.cycle, fresh_dir, program=built.program)
    pipeline.get_module_view("top.rv.dp", start.cycle, fresh_dir, program=built.program)


def test_the_same_source_is_built_once(fresh_dir: Path, user_dir: Path) -> None:
    source = ACCEPTED["recursion"][0]
    first = pipeline.build_user_program(source, fresh_dir)
    again = pipeline.build_user_program(source, fresh_dir)
    assert again.program == first.program and again.cached
    other = pipeline.build_user_program(source + "// changed\n", fresh_dir)
    assert other.program != first.program


@pytest.mark.parametrize("name", sorted(TOO_BIG))
def test_oversized_or_odd_source_is_refused_before_building(
    name: str, fresh_dir: Path, user_dir: Path
) -> None:
    source, message = TOO_BIG[name]
    with pytest.raises(ProgramRejectedError, match=message):
        pipeline.build_user_program(source, fresh_dir)
    assert not user_dir.exists() or not any(user_dir.iterdir())


@pytest.mark.parametrize("name", sorted(OUTSIDE_SUBSET))
def test_a_rejected_program_leaves_nothing_behind(
    name: str, fresh_dir: Path, user_dir: Path
) -> None:
    source, message = OUTSIDE_SUBSET[name]
    with pytest.raises(ProgramRejectedError, match=message) as caught:
        pipeline.build_user_program(source, fresh_dir)
    assert "u_" not in str(caught.value), "the message names the user's file, not our name"
    assert pipeline.USER_SOURCE_FILE in str(caught.value) or name == "no_halt"
    assert pipeline.list_user_programs() == []


def test_one_build_at_a_time(fresh_dir: Path, user_dir: Path) -> None:
    started, release = threading.Event(), threading.Event()

    def hold() -> None:
        with pipeline.BUILD_LOCK:
            started.set()
            release.wait(10)

    holder = threading.Thread(target=hold)
    holder.start()
    started.wait(10)
    try:
        with pytest.raises(BuildBusyError, match="another program is being built"):
            pipeline.build_user_program(ACCEPTED["fibonacci"][0], fresh_dir)
    finally:
        release.set()
        holder.join()
    assert pipeline.build_user_program(ACCEPTED["fibonacci"][0], fresh_dir).program


def test_old_user_programs_are_removed(
    fresh_dir: Path, user_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "MAX_USER_PROGRAMS", 2)
    names = [
        pipeline.build_user_program(f"int main(void) {{ return {n}; }}\n", fresh_dir).program
        for n in (1, 2, 3)
    ]
    assert pipeline.list_user_programs() == sorted(names[1:])
    with pytest.raises(KeyError):
        pipeline.get_golden(fresh_dir, program=names[0])


def test_user_programs_are_not_listed_with_the_examples(fresh_dir: Path, user_dir: Path) -> None:
    pipeline.build_user_program("int main(void) { return 4; }\n", fresh_dir)
    assert pipeline.list_programs(fresh_dir) == ["sum", "tour"]


def test_an_unknown_user_program_is_a_key_error(fresh_dir: Path, user_dir: Path) -> None:
    with pytest.raises(KeyError):
        pipeline.get_golden(fresh_dir, program="u_0123456789abcdef")
