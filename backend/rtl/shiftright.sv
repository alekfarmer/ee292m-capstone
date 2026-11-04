// Logarithmic right shifter: stage k shifts by 2^k when shamt[k] is 1,
// filling with `fill` (0 for srl, the sign bit a[31] for sra).
module shiftright (
    input  logic [31:0] a,
    input  logic [4:0]  shamt,
    input  logic        fill,
    output logic [31:0] y
);
    logic [31:0] s1, s2, s4, s8;

    mux2 by1  (.d0(a),  .d1({fill,        a[31:1]}),   .s(shamt[0]), .y(s1));
    mux2 by2  (.d0(s1), .d1({{2{fill}},   s1[31:2]}),  .s(shamt[1]), .y(s2));
    mux2 by4  (.d0(s2), .d1({{4{fill}},   s2[31:4]}),  .s(shamt[2]), .y(s4));
    mux2 by8  (.d0(s4), .d1({{8{fill}},   s4[31:8]}),  .s(shamt[3]), .y(s8));
    mux2 by16 (.d0(s8), .d1({{16{fill}},  s8[31:16]}), .s(shamt[4]), .y(y));
endmodule
