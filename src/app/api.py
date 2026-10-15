"""HTTP routes only. Each route calls one pipeline entry point."""

from typing import Annotated

from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from app import pipeline
from app.errors import ArtifactMissingError, PipelineError
from app.models import (
    AdderCaseInfo,
    AdderView,
    GateCountReport,
    GoldenArtifact,
    Health,
    ProgramArtifact,
)
from app.paths import VENDOR_DIR, WEB_DIR

app = FastAPI(
    title="C to Gates",
    description="Artifacts for following one C program down to logic gates.",
    version="0.1.0",
)

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


@app.get("/api/program")
def program() -> ProgramArtifact:
    """The fixed C program, its asm listing and memory layout (M1)."""
    return pipeline.get_program()


@app.get("/api/golden")
def golden() -> GoldenArtifact:
    """Spike's commit log for the fixed program (M1)."""
    return pipeline.get_golden()


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


if VENDOR_DIR.is_dir():
    app.mount("/vendor", StaticFiles(directory=VENDOR_DIR), name="vendor")
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
