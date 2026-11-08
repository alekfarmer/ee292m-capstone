"""Programs outside the subset are rejected with a clear message."""

from pathlib import Path

import pytest

from app import pipeline, software
from app.errors import ProgramRejectedError

REJECTED = {
    "float": (
        "int main(void) { float x = 2; return (int)x; }",
        "floating-point",
    ),
    "double_literal": ("int main(void) { int x = 1.5e0; return x; }", "floating-point literal"),
    "multiply": ("int main(void) { int a = 3; return a * a; }", "M extension"),
    "divide": ("int main(void) { int a = 9; return a / 3; }", "M extension"),
    "remainder": ("int main(void) { int a = 9; return a % 4; }", "M extension"),
    "libc_call": ("int puts(int c);\nint main(void) { return puts(1); }", "libc"),
    "libc_header": ("#include <stdio.h>\nint main(void) { return 0; }", "no preprocessor"),
    "image_too_big": (
        "int big[2000];\nint main(void) { big[1999] = 1; return big[1999]; }",
        "does not fit in RAM",
    ),
    "no_halt": ("int g;\nint main(void) { while (1) { g = g + 1; } }", "did not halt within 500"),
    "syntax_error": ("int main(void) { return 0 }", "compile error"),
}


@pytest.mark.parametrize("name", sorted(REJECTED))
def test_rejected(name: str, tmp_path: Path) -> None:
    source, message = REJECTED[name]
    c_file = tmp_path / f"{name}.c"
    c_file.write_text(source + "\n")
    with pytest.raises(ProgramRejectedError, match=message):
        pipeline.build_program_artifacts(c_file, tmp_path / "out", tmp_path / "work")


SECRET = "SECRET_TOKEN=do-not-show-me"

# Ways C source can ask the compiler to read another file. Each must be
# refused before any tool runs, so the file's text can never reach a message.
READS_A_FILE = {
    "include_by_path": ('#include "{secret}"\nint main(void) {{ return 0; }}', "'#'"),
    "include_after_comment": (
        '/* */ #include "{secret}"\nint main(void) {{ return 0; }}',
        "'#'",
    ),
    "include_by_digraph": ('%:include "{secret}"\nint main(void) {{ return 0; }}', "'%:'"),
    "include_by_trigraph": ('??=include "{secret}"\nint main(void) {{ return 0; }}', "'\\?\\?='"),
    "asm_incbin": (
        'int main(void) {{ __asm__(".incbin \\"{secret}\\""); return 0; }}',
        "inline assembly",
    ),
    "asm_spliced": (
        'int main(void) {{ as\\\nm(".incbin \\"{secret}\\""); return 0; }}',
        "inline assembly",
    ),
    "pragma_operator": (
        'int main(void) {{ _Pragma("GCC dependency \\"{secret}\\"") return 0; }}',
        "_Pragma",
    ),
}


@pytest.mark.parametrize("name", sorted(READS_A_FILE))
def test_source_cannot_read_another_file(name: str, tmp_path: Path) -> None:
    secret_file = tmp_path / "secret.env"
    secret_file.write_text(SECRET + "\n")
    template, message = READS_A_FILE[name]
    c_file = tmp_path / f"{name}.c"
    c_file.write_text(template.format(secret=secret_file) + "\n")
    with pytest.raises(ProgramRejectedError, match=message) as caught:
        software.check_source_text(c_file.read_text(), c_file.name)
    assert SECRET not in str(caught.value)
    # The whole pipeline refuses it too, with the same message.
    with pytest.raises(ProgramRejectedError, match=message) as caught:
        pipeline.build_program_artifacts(c_file, tmp_path / "out", tmp_path / "work")
    assert SECRET not in str(caught.value)


def test_words_in_comments_are_fine(tmp_path: Path) -> None:
    """'asm' in a comment is not inline assembly."""
    c_file = tmp_path / "words.c"
    c_file.write_text("// the asm pane shows this\nint main(void) { return 3; }\n")
    _, golden = pipeline.build_program_artifacts(c_file, tmp_path / "out", tmp_path / "work")
    assert golden.exit_code == 3


def test_operators_inside_comments_are_fine(tmp_path: Path) -> None:
    c_file = tmp_path / "comments.c"
    c_file.write_text("/* a * b / c % d */\nint main(void) { return 7; } // 2 * 3\n")
    _, golden = pipeline.build_program_artifacts(c_file, tmp_path / "out", tmp_path / "work")
    assert golden.exit_code == 7


def test_rejection_names_the_line(tmp_path: Path) -> None:
    c_file = tmp_path / "line.c"
    c_file.write_text("int main(void) {\n  int a = 2;\n  return a * 2;\n}\n")
    with pytest.raises(ProgramRejectedError, match=r"line\.c:3:"):
        pipeline.build_program_artifacts(c_file, tmp_path / "out", tmp_path / "work")
