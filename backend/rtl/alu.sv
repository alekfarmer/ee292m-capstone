// RV32I ALU. Addition, subtraction and both set-less-than operations use the
// structural ripple-carry adder32; a - b is computed as a + ~b + 1.
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

    assign zero = (sum == 32'b0);
    assign neg  = sum[31];
    assign ovf  = (a[31] == b_eff[31]) & (sum[31] != a[31]);
    assign lt   = neg ^ ovf;
    assign ltu  = ~carry;

    always_comb begin
        case (alucontrol)
            4'b0000: result = sum;
            4'b0001: result = sum;
            4'b0010: result = a & b;
            4'b0011: result = a | b;
            4'b0100: result = a ^ b;
            4'b0101: result = {31'b0, lt};
            4'b0110: result = {31'b0, ltu};
            4'b0111: result = a << b[4:0];
            4'b1000: result = a >> b[4:0];
            4'b1001: result = $signed(a) >>> b[4:0];
            default: result = 32'b0;
        endcase
    end
endmodule
