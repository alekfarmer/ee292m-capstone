// ALU result select: picks one unit's output by alucontrol (see alu.sv),
// as a tree of 2:1 multiplexers.
//
//   alucontrol[3] = 0: alucontrol[2:0] picks one of eight, three levels deep
//     000/001 sum   010 and   011 or   100 xor   101 slt   110 sltu   111 sll
//   alucontrol[3] = 1: alucontrol[0] picks srl (1000) or sra (1001)
//
// Codes 1010-1111 are never produced by aludec; they give srl or sra.
module resultmux (
    input  logic [3:0]  alucontrol,
    input  logic [31:0] sum,
    input  logic [31:0] y_and,
    input  logic [31:0] y_or,
    input  logic [31:0] y_xor,
    input  logic        lt,
    input  logic        ltu,
    input  logic [31:0] y_sll,
    input  logic [31:0] y_srl,
    input  logic [31:0] y_sra,
    output logic [31:0] result
);
    logic [31:0] and_or, xor_slt, sltu_sll, low4, high4, first8, shr;

    // Level 1: alucontrol[0] (000 and 001 are both the sum).
    mux2 m_and_or   (.d0(y_and),         .d1(y_or),  .s(alucontrol[0]), .y(and_or));
    mux2 m_xor_slt  (.d0(y_xor),         .d1({31'b0, lt}), .s(alucontrol[0]), .y(xor_slt));
    mux2 m_sltu_sll (.d0({31'b0, ltu}),  .d1(y_sll), .s(alucontrol[0]), .y(sltu_sll));
    mux2 m_shr      (.d0(y_srl),         .d1(y_sra), .s(alucontrol[0]), .y(shr));
    // Level 2: alucontrol[1].
    mux2 m_low4     (.d0(sum),     .d1(and_or),   .s(alucontrol[1]), .y(low4));
    mux2 m_high4    (.d0(xor_slt), .d1(sltu_sll), .s(alucontrol[1]), .y(high4));
    // Level 3: alucontrol[2], then alucontrol[3] chooses the right shifts.
    mux2 m_first8   (.d0(low4),   .d1(high4), .s(alucontrol[2]), .y(first8));
    mux2 m_result   (.d0(first8), .d1(shr),   .s(alucontrol[3]), .y(result));
endmodule
