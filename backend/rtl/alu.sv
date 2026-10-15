// RV32I ALU, built from blocks so each can be drawn on its own:
//   adder32   a + b or a + ~b + 1 (structural ripple carry)
//   logicunit and / or / xor
//   shifter   sll / srl / sra
//   resultmux picks the result by alucontrol
//
// alucontrol: 0000 add  0001 sub  0010 and  0011 or   0100 xor
//             0101 slt  0110 sltu 0111 sll  1000 srl  1001 sra
//
// Flags describe the adder result (used by the branch logic after a sub):
//   zero = sum == 0, neg = sum[31], ovf = signed overflow, carry = carry out
//   (for a subtraction carry = 1 means no borrow, i.e. a >= b unsigned).
module alu (
    input  logic [31:0] a,
    input  logic [31:0] b,
    input  logic [3:0]  alucontrol,
    output logic [31:0] result,
    output logic        zero,
    output logic        neg,
    output logic        ovf,
    output logic        carry
);
    logic        sub;
    logic [31:0] b_eff;
    logic [31:0] sum;
    logic        lt;
    logic        ltu;
    logic [31:0] y_and, y_or, y_xor;
    logic [31:0] y_sll, y_srl, y_sra;

    // Subtract for sub, slt and sltu.
    assign sub   = (alucontrol == 4'b0001) | (alucontrol == 4'b0101) | (alucontrol == 4'b0110);
    assign b_eff = sub ? ~b : b;

    adder32 add (
        .a   (a),
        .b   (b_eff),
        .cin (sub),
        .s   (sum),
        .cout(carry)
    );

    logicunit lu (.a(a), .b(b), .y_and(y_and), .y_or(y_or), .y_xor(y_xor));

    shifter sh (.a(a), .shamt(b[4:0]), .y_sll(y_sll), .y_srl(y_srl), .y_sra(y_sra));

    assign zero = (sum == 32'b0);
    assign neg  = sum[31];
    assign ovf  = (a[31] == b_eff[31]) & (sum[31] != a[31]);
    assign lt   = neg ^ ovf;
    assign ltu  = ~carry;

    resultmux rm (
        .alucontrol(alucontrol), .sum(sum),
        .y_and(y_and), .y_or(y_or), .y_xor(y_xor),
        .lt(lt), .ltu(ltu),
        .y_sll(y_sll), .y_srl(y_srl), .y_sra(y_sra),
        .result(result)
    );
endmodule
