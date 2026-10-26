// Bitwise logic: AND, OR and XOR of a and b, computed in parallel.
module logicunit (
    input  logic [31:0] a,
    input  logic [31:0] b,
    output logic [31:0] y_and,
    output logic [31:0] y_or,
    output logic [31:0] y_xor
);
    assign y_and = a & b;
    assign y_or  = a | b;
    assign y_xor = a ^ b;
endmodule
