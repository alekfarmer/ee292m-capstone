"""The interfaces between modules, as README and ARCHITECTURE describe them.

Each test fails when a module reaches past its one narrow interface.
"""

import ast
import re
from pathlib import Path

from app.paths import REPO_ROOT

APP = REPO_ROOT / "src" / "app"
WEB = REPO_ROOT / "src" / "web"

# Shared definitions every module may use: types, errors, fixed paths.
SHARED = {"models", "errors", "paths"}


def module_files(module: str) -> list[Path]:
    """The source of ``app.<module>``: one file, or every file of a package."""
    package = APP / module
    return sorted(package.rglob("*.py")) if package.is_dir() else [APP / f"{module}.py"]


def app_imports(module: str) -> set[str]:
    """The other ``app.*`` modules that ``app.<module>`` (file or package) imports."""
    found: set[str] = set()
    for path in module_files(module):
        found |= _app_imports_of(ast.parse(path.read_text()))
    return found - {module}


def _app_imports_of(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "app":
                found.update(alias.name for alias in node.names)
            elif node.module.startswith("app."):
                found.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            found.update(a.name.split(".")[1] for a in node.names if a.name.startswith("app."))
    return found


def stdlib_imports(path: Path) -> set[str]:
    """Top-level modules imported by ``path``."""
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def test_the_api_and_cli_only_talk_to_the_pipeline() -> None:
    """Both adapters go through the facade, never to the steps behind it."""
    for adapter in ("api", "cli"):
        extra = app_imports(adapter) - {"pipeline"} - SHARED
        assert not extra, f"{adapter}.py bypasses pipeline.py: imports {sorted(extra)}"


def test_only_tools_starts_external_programs() -> None:
    """Every gcc, objdump, Spike, Yosys, Icarus and Chromium call goes through tools.py."""
    offenders = [
        p.name
        for p in sorted(APP.rglob("*.py"))
        if p.name != "tools.py" and {"subprocess", "os"} & stdlib_imports(p)
    ]
    assert not offenders, f"start external programs outside tools.py: {offenders}"


def test_the_pipeline_steps_do_not_call_back_up() -> None:
    """The steps behind the facade never import the facade or the adapters."""
    steps = ("software", "hardware", "simulate", "views", "render", "decode", "vcd", "tools")
    for step in steps:
        upward = app_imports(step) & {"pipeline", "api", "cli", "smoke", "pagecheck", "regression"}
        assert not upward, f"{step}.py imports {sorted(upward)}"


def test_the_page_only_talks_to_the_api() -> None:
    """The page fetches /api/ and nothing else; it has one fetch helper."""
    js = "\n".join(p.read_text() for p in sorted(WEB.glob("*.js")))
    assert js.count("fetch(") == 1, "the page should fetch through one helper (getJson)"
    for url in re.findall(r"getJson\(\s*[`'\"]([^`'\"]*)", js):
        assert url.startswith("/api/"), f"the page fetches {url}, outside the API"
