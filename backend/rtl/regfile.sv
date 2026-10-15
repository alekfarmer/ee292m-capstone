// Register file: 32 x 32 bits, two combinational read ports, one write port
// written on the rising clock edge. x0 always reads 0. All registers start
// at 0, as in Spike once crt0 has cleared what the boot ROM left behind.
// Synthesis keeps this module as a black box (see synth.ys).
module regfile (
    input  logic        clk,
    input  logic        we3,
    input  logic [4:0]  a1,
    input  logic [4:0]  a2,
    input  logic [4:0]  a3,
    input  logic [31:0] wd3,
    output logic [31:0] rd1,
    output logic [31:0] rd2
);
    logic [31:0] rf [31:1];

    integer i;
    initial begin
        for (i = 1; i < 32; i = i + 1) rf[i] = 32'b0;
    end

    always_ff @(posedge clk) begin
        if (we3 && a3 != 5'd0) rf[a3] <= wd3;
    end

    assign rd1 = (a1 != 5'd0) ? rf[a1] : 32'b0;
    assign rd2 = (a2 != 5'd0) ? rf[a2] : 32'b0;
endmodule
