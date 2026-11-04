"""HTTP routes only. Each route calls one pipeline entry point."""

from typing import Annotated

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Scope

from app import pipeline
from app.errors import ArtifactMissingError, PipelineError
from app.models import (
    AdderCaseInfo,
    AdderView,
    CycleView,
    GateCountReport,
    GoldenArtifact,
    Health,
    ModuleView,
    ProgramArtifact,
    StartCycle,
    TraceArtifact,
)
from app.paths import VENDOR_DIR, WEB_DIR

app = FastAPI(
    title="C to Gates",
    description="Artifacts for following one C program down to logic gates.",
    version="0.1.0",
)

ViewPath = Annotated[
    str,
    Path(
        pattern=r"^top(\.[A-Za-z_][A-Za-z0-9_]*){0,8}$",
        description="instance path, e.g. 'top.rv.dp' (the datapath)",
    ),
]
CycleNo = Annotated[int, Query(ge=0, le=100_000, description="cycle number, 0 = first instruction")]
ProgramName = Annotated[
    str,
    Query(pattern=r"^[a-z][a-z0-9_]{0,31}$", description="program name, e.g. 'sum'"),
]
CaseId = Annotated[str, Path(pattern=r"^[a-z0-9_]{1,64}$", description="adder case id")]


@app.exception_handler(ArtifactMissingError)
async def _artifact_missing(_: Request, exc: ArtifactMissingError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(PipelineError)
async def _pipeline_error(_: Request, exc: PipelineError) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/api/health")
def health() -> Health:
    """Liveness check."""
    return Health(status="ok")


@app.get("/api/programs")
def programs() -> list[str]:
    """The programs that have artifacts, by name (e.g. 'sum')."""
    return pipeline.list_programs()


def _unknown_program(name: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"no program '{name}' has been built")


@app.get("/api/program")
def program(program: ProgramName = pipeline.DEFAULT_PROGRAM) -> ProgramArtifact:
    """A program's C source, asm listing and memory layout (M1)."""
    try:
        return pipeline.get_program(program=program)
    except KeyError:
        raise _unknown_program(program) from None


@app.get("/api/golden")
def golden(program: ProgramName = pipeline.DEFAULT_PROGRAM) -> GoldenArtifact:
    """Spike's commit log for a program (M1)."""
    try:
        return pipeline.get_golden(program=program)
    except KeyError:
        raise _unknown_program(program) from None


@app.get("/api/start")
def start(program: ProgramName = pipeline.DEFAULT_PROGRAM) -> StartCycle:
    """The cycle the page opens on, where the C, assembly and hardware line up (M3)."""
    try:
        return pipeline.get_start_cycle(program=program)
    except KeyError:
        raise _unknown_program(program) from None


@app.get("/api/trace")
def trace(program: ProgramName = pipeline.DEFAULT_PROGRAM) -> TraceArtifact:
    """Every net's value in every cycle of a program's gate-level run (M2)."""
    try:
        return pipeline.get_trace(program=program)
    except KeyError:
        raise _unknown_program(program) from None


@app.get("/api/cycle/{n}")
def cycle(
    n: Annotated[int, Path(ge=0, le=100_000)],
    program: ProgramName = pipeline.DEFAULT_PROGRAM,
) -> CycleView:
    """What runs in cycle n, its register write, and the C-line step targets (M3)."""
    try:
        return pipeline.get_cycle_view(n, program=program)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"no program '{program}' or no cycle {n} in its trace"
        ) from None


@app.get("/api/view/{path}")
def module_view(
    path: ViewPath, cycle: CycleNo = 0, program: ProgramName = pipeline.DEFAULT_PROGRAM
) -> ModuleView:
    """One module (blocks or gates) with every wire's value in a cycle (M3)."""
    try:
        return pipeline.get_module_view(path, cycle, program=program)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"no program '{program}', no instance '{path}' or no cycle {cycle}",
        ) from None


@app.get("/api/gate-counts")
def gate_counts() -> GateCountReport:
    """Gate counts per module of the synthesized core (M0)."""
    return pipeline.get_gate_counts()


@app.get("/api/adder")
def adder_cases() -> list[AdderCaseInfo]:
    """The adder input cases available (M0)."""
    return pipeline.list_adder_cases()


@app.get("/api/adder/{case_id}")
def adder_view(case_id: CaseId) -> AdderView:
    """One adder case: values from the gate netlist and the SVG drawing (M0)."""
    try:
        return pipeline.get_adder_view(case_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no adder case '{case_id}'") from None


class PageFiles(StaticFiles):
    """Static files a browser must revalidate before each use.

    Without this, a browser may keep running an old graph.js after an update.
    `no-cache` still lets it keep the file; unchanged files cost a 304.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Serve the file as StaticFiles does, marked `Cache-Control: no-cache`."""
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


if VENDOR_DIR.is_dir():
    app.mount("/vendor", StaticFiles(directory=VENDOR_DIR), name="vendor")
app.mount("/", PageFiles(directory=WEB_DIR, html=True), name="web")
