// 1 when every bit of a is 0: an OR of all 32 bits, inverted.
module zerodetect (
    input  logic [31:0] a,
    output logic        zero
);
    assign zero = ~|a;
endmodule
