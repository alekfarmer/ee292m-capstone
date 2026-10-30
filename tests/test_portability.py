"""The checkout works the same on every host, Windows included.

The committed artifacts are compared byte for byte with freshly generated
ones, so a checkout that turned their line endings into CRLF would make every
staleness test fail with a misleading message. These tests name the real cause.
"""

from pathlib import Path

from app.paths import ARTIFACTS_DIR, BACKEND, REPO_ROOT

# Directories whose files are generated from, or compared with, the sources.
CHECKED_DIRS = [ARTIFACTS_DIR, BACKEND / "rtl", BACKEND / "programs", REPO_ROOT / "src", REPO_ROOT / "tests"]

CRLF_HINT = (
    "has Windows (CRLF) line endings. .gitattributes keeps LF on every machine, "
    "but a clone made before it was added keeps CRLF: clone the repository again "
    "(see 'Windows' in the README)."
)


def text_files(root: Path) -> list[Path]:
    """Every file under ``root``, skipping Python's bytecode caches."""
    return [p for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts]


def test_gitattributes_keeps_lf_endings() -> None:
    """Git checks out LF everywhere, whatever the user's git settings."""
    rules = (REPO_ROOT / ".gitattributes").read_text().split("\n")
    assert "* text=auto eol=lf" in rules


def test_checked_out_files_have_lf_endings() -> None:
    """No source or committed artifact was checked out with CRLF endings."""
    for root in CHECKED_DIRS:
        files = text_files(root)
        assert files, f"nothing found under {root}"
        for path in files:
            crlf = b"\r\n" in path.read_bytes()
            assert not crlf, f"{path.relative_to(REPO_ROOT)} {CRLF_HINT}"
