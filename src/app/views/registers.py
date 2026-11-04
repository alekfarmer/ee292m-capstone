"""The register file, shown as a table of its 32 registers in one cycle.

The register file is memory, not logic: synthesis keeps it as a black box
and the gate-level run uses its behavioural model (regfile.sv), so it is
shown as a table rather than as gates. Every value comes from the trace.
"""

from typing import Literal

from app.decode import ABI_NAMES
from app.errors import PipelineError
from app.models import RegisterRow
from app.views.trace import TraceIndex

REGFILE_MODULE = "regfile"
REGISTERS = 32


def _hex32(value: int) -> str:
    return f"0x{value:08x}"


def register_value(prefix: str, n: int, cycle: int, index: TraceIndex) -> int:
    """Register ``xn``'s contents during ``cycle``.

    The simulator records a register only once something is stored in it, so
    a register missing from the trace still holds the 0 every register starts
    with (regfile.sv). That holds only if no cycle stores into it, which is
    checked here.

    Raises:
        PipelineError: a register missing from the trace is written in some cycle.
    """
    if n == 0:
        return 0
    signal = f"{prefix}rf[{n}]"
    if signal in index.widths:
        return index.value(cycle, signal)
    for k in range(len(index.cycles)):
        if index.value(k, prefix + "we3") == 1 and index.value(k, prefix + "a3") == n:
            raise PipelineError(f"x{n} is written in cycle {k} but is missing from the trace")
    return 0


def register_rows(prefix: str, cycle: int, index: TraceIndex) -> list[RegisterRow]:
    """All 32 registers in ``cycle``, with the ports that read and write them.

    ``prefix`` is the register file's instance path relative to ``top``, with
    a trailing dot (``rv.dp.rf.``).
    """
    a1 = index.value(cycle, prefix + "a1")
    a2 = index.value(cycle, prefix + "a2")
    a3 = index.value(cycle, prefix + "a3")
    we = index.value(cycle, prefix + "we3") == 1
    wd = index.value(cycle, prefix + "wd3")
    rows = []
    for n in range(REGISTERS):
        read_by: list[Literal["rd1", "rd2"]] = []
        if a1 == n:
            read_by.append("rd1")
        if a2 == n:
            read_by.append("rd2")
        rows.append(
            RegisterRow(
                index=n,
                name=ABI_NAMES[n],
                value=_hex32(register_value(prefix, n, cycle, index)),
                read_by=read_by,
                written=_hex32(wd) if we and n == a3 and n != 0 else None,
            )
        )
    return rows
