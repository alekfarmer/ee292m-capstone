// Testbench for the RTL reference simulation (Icarus Verilog).
// Reset is high for the first rising edge (loading the PC), then the core
// runs `CYCLES more cycles. Every signal under dut goes to rtl.vcd.
`timescale 1ns / 1ns
module tb_rtl;
    logic clk = 1'b0;
    logic reset = 1'b1;

    top dut (.clk(clk), .reset(reset));

    always #5 clk = ~clk;

    initial begin
        $dumpfile("rtl.vcd");
        $dumpvars(0, dut);
        @(posedge clk);
        #1 reset = 1'b0;
        repeat (`CYCLES) @(posedge clk);
        #1 $finish;
    end
endmodule
