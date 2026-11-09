"""Fixed locations inside the repository (mounted at /work in the container)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
RTL_DIR = BACKEND / "rtl"
PROGRAMS_DIR = BACKEND / "programs"
ARTIFACTS_DIR = BACKEND / "artifacts"
BUILD_DIR = BACKEND / "build"  # scratch space, gitignored
USER_DIR = BUILD_DIR / "user"  # programs entered on the page (M5), built live
WEB_DIR = REPO_ROOT / "src" / "web"
VENDOR_DIR = Path("/opt/vendor")  # frontend libraries, installed in the image

SYNTH_SCRIPT = RTL_DIR / "synth.ys"
CRT0 = PROGRAMS_DIR / "crt0.S"
LINKER_SCRIPT = PROGRAMS_DIR / "link.ld"
SUM_PROGRAM = PROGRAMS_DIR / "sum.c"
