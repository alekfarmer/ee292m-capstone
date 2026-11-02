"""The image's fingerprint (the tag `make pull` asks for) covers what the image is built from.

The Makefile hashes ``IMAGE_INPUTS``; if the Dockerfile copied a file from
``docker/`` that is not among them, an image built from an older version of
that file would carry the same tag and be pulled as if it matched.
"""

import re

from app.paths import REPO_ROOT

DOCKER = REPO_ROOT / "docker"


def image_inputs() -> set[str]:
    """The files the Makefile fingerprints, relative to the repository."""
    makefile = (REPO_ROOT / "Makefile").read_text()
    m = re.search(r"^IMAGE_INPUTS := (.+)$", makefile, re.MULTILINE)
    assert m, "the Makefile no longer defines IMAGE_INPUTS"
    return set(m.group(1).split())


def copied_from_the_context() -> set[str]:
    """Every file the Dockerfile COPYs or ADDs from docker/ (not from another stage)."""
    copied: set[str] = set()
    for line in (DOCKER / "Dockerfile").read_text().splitlines():
        words = line.split()
        if not words or words[0] not in ("COPY", "ADD"):
            continue
        if any(w.startswith("--from=") for w in words):
            continue
        sources = [w for w in words[1:-1] if not w.startswith("--")]
        copied.update(f"docker/{s}" for s in sources)
    return copied


def test_the_fingerprint_covers_every_file_the_image_copies() -> None:
    copied = copied_from_the_context()
    assert copied, "found no COPY from docker/; has the Dockerfile moved?"
    missing = copied - image_inputs()
    assert not missing, f"add {sorted(missing)} to IMAGE_INPUTS in the Makefile"


def test_the_fingerprint_covers_the_dockerfile_and_only_real_files() -> None:
    inputs = image_inputs()
    assert "docker/Dockerfile" in inputs
    assert all((REPO_ROOT / f).is_file() for f in inputs), sorted(inputs)
