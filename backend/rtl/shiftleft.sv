// Logarithmic left shifter: stage k shifts by 2^k when shamt[k] is 1,
// filling with 0s. The shifts themselves are only wiring.
module shiftleft (
    input  logic [31:0] a,
    input  logic [4:0]  shamt,
    output logic [31:0] y
);
    logic [31:0] s1, s2, s4, s8;

    mux2 by1  (.d0(a),  .d1({a[30:0],  1'b0}),  .s(shamt[0]), .y(s1));
    mux2 by2  (.d0(s1), .d1({s1[29:0], 2'b0}),  .s(shamt[1]), .y(s2));
    mux2 by4  (.d0(s2), .d1({s2[27:0], 4'b0}),  .s(shamt[2]), .y(s4));
    mux2 by8  (.d0(s4), .d1({s4[23:0], 8'b0}),  .s(shamt[3]), .y(s8));
    mux2 by16 (.d0(s8), .d1({s8[15:0], 16'b0}), .s(shamt[4]), .y(y));
endmodule
