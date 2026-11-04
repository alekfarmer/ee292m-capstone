// Invert every bit of b when `invert` is 1 (a row of XOR gates). With a
// carry in of 1 this turns the adder's a + b into a - b.
module binvert (
    input  logic [31:0] b,
    input  logic        invert,
    output logic [31:0] y
);
    assign y = b ^ {32{invert}};
endmodule
