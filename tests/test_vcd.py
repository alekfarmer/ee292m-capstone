"""The VCD reader samples each cycle just before its rising clock edge."""

from app.vcd import read_timeline, sample_cycles

VCD = """$timescale 1ns $end
$scope module top $end
$var wire 1 ! clk $end
$var wire 1 " reset $end
$var wire 4 # q [3:0] $end
$scope module \\g_bit[0].fa $end
$var wire 1 $ s $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0!
1"
bx #
x$
$end
#5
1!
b0000 #
0$
#6
0"
#10
0!
#15
1!
b0001 #
1$
#20
0!
#25
1!
b0010 #
"""


def test_cycles_are_sampled_before_each_rising_edge_after_reset() -> None:
    cycles = sample_cycles(read_timeline(VCD), "top.clk", "top.reset", strip_prefix="top.")
    # Edge at 5 is in reset (skipped); edges at 15 and 25 close cycles 0 and 1.
    assert [c["q"] for c in cycles] == [0b0000, 0b0001]
    assert [c["g_bit[0].fa.s"] for c in cycles] == [0, 1]


def test_unknown_values_are_none() -> None:
    timeline = read_timeline(VCD)
    first = dict(timeline.steps[0][1])
    assert first["top.q"] is None and first["top.g_bit[0].fa.s"] is None
    assert timeline.widths["top.q"] == 4
