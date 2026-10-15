// 32-bit register with synchronous reset (the program counter).
module flopr (
    input  logic        clk,
    input  logic        reset,
    input  logic [31:0] d,
    output logic [31:0] q
);
    localparam logic [31:0] RESET_VALUE = 32'h8000_0000;  // start of RAM

    always_ff @(posedge clk) begin
        if (reset) q <= RESET_VALUE;
        else       q <= d;
    end
endmodule
