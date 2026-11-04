"""What the page draws, per cycle, built from the netlist and the trace.

* :mod:`app.views.trace`: the verified trace, one snapshot per cycle.
* :mod:`app.views.cycle`: what the panes show per cycle, and the start cycle.
* :mod:`app.views.module`: one module as a graph of blocks or gates (or the
  ALU adder's textbook drawing), with every wire's value in a cycle.
* :mod:`app.views.registers`: the register file as a table.

Every value comes from trace.json (the verified gate-level run).
"""

from app.views.cycle import (
    FIRST_C_LINE,
    FIRST_CYCLE,
    LOOPS_BACK,
    Step,
    can_close_a_loop,
    cycle_view,
    program_start,
    start_cycle,
)
from app.views.module import (
    DEFAULT_VIEW,
    GATE_MODULES,
    GATE_PORTS,
    ROOT,
    adder_case_from_trace,
    drill_kind,
    module_view,
    resolve,
    view_paths,
)
from app.views.trace import TraceIndex, expand_trace, trace_index

__all__ = [
    "DEFAULT_VIEW",
    "FIRST_CYCLE",
    "FIRST_C_LINE",
    "GATE_MODULES",
    "GATE_PORTS",
    "LOOPS_BACK",
    "ROOT",
    "Step",
    "TraceIndex",
    "adder_case_from_trace",
    "can_close_a_loop",
    "cycle_view",
    "drill_kind",
    "expand_trace",
    "module_view",
    "program_start",
    "resolve",
    "start_cycle",
    "trace_index",
    "view_paths",
]
