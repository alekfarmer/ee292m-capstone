// Barrel shifter: all three RV32I shifts of a by shamt, computed in parallel.
// Each is five stages of 2:1 multiplexers (see shiftleft.sv, shiftright.sv);
// the two right shifts differ only in the bit they shift in.
module shifter (
    input  logic [31:0] a,
    input  logic [4:0]  shamt,
    output logic [31:0] y_sll,
    output logic [31:0] y_srl,
    output logic [31:0] y_sra
);
    shiftleft  lsl (.a(a), .shamt(shamt), .y(y_sll));
    shiftright lsr (.a(a), .shamt(shamt), .fill(1'b0), .y(y_srl));
    shiftright asr (.a(a), .shamt(shamt), .fill(a[31]), .y(y_sra));
endmodule
