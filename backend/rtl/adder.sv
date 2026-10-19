// 32-bit adder for PC + 4 and PC + imm. Written behaviourally: only the
// ALU's adder (adder32) is kept as a structural ripple-carry chain.
module adder (
    input  logic [31:0] a,
    input  logic [31:0] b,
    output logic [31:0] y
);
    assign y = a + b;
endmodule
