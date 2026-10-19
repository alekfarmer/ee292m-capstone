// Single-cycle RV32I processor: controller + datapath.
module riscvsingle (
    input  logic        clk,
    input  logic        reset,
    output logic [31:0] pc,
    input  logic [31:0] instr,
    output logic        memwrite,
    output logic [3:0]  byteen,
    output logic [31:0] aluresult,
    output logic [31:0] writedata,
    input  logic [31:0] readword
);
    logic [1:0] resultsrc, pcsrc, srcasel;
    logic       alusrc, regwrite;
    logic [2:0] immsrc;
    logic [3:0] alucontrol;
    logic       zero, neg, ovf, carry;

    controller c (
        .op(instr[6:0]), .funct3(instr[14:12]), .funct7b5(instr[30]),
        .zero(zero), .neg(neg), .ovf(ovf), .carry(carry),
        .resultsrc(resultsrc), .memwrite(memwrite), .pcsrc(pcsrc),
        .srcasel(srcasel), .alusrc(alusrc), .regwrite(regwrite),
        .immsrc(immsrc), .alucontrol(alucontrol)
    );

    datapath dp (
        .clk(clk), .reset(reset),
        .resultsrc(resultsrc), .pcsrc(pcsrc), .srcasel(srcasel),
        .alusrc(alusrc), .regwrite(regwrite), .immsrc(immsrc),
        .alucontrol(alucontrol),
        .zero(zero), .neg(neg), .ovf(ovf), .carry(carry),
        .pc(pc), .instr(instr), .aluresult(aluresult),
        .writedata(writedata), .byteen(byteen), .readword(readword)
    );
endmodule
