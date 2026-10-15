"""Errors raised by the pipelines. Each carries one plain message for the user."""


class PipelineError(Exception):
    """A pipeline step failed; ``str(error)`` is safe to show to the user."""


class ToolError(PipelineError):
    """An external tool (gcc, objdump, Spike, Yosys) failed unexpectedly."""


class ProgramRejectedError(PipelineError):
    """The C program is outside the supported subset or cannot run on the core."""


class ArtifactMissingError(PipelineError):
    """A generated artifact is missing; run ``make artifacts``."""
