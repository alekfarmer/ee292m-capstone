// Single-cycle RV32I datapath (after Harris & Harris, DDCA RISC-V Edition,
// ch. 7), extended to the full RV32I base: lui/auipc via srcasel, jalr via
// pcsrc = 10, and byte/halfword memory access via the lsu.
module datapath (
    input  logic        clk,
    input  logic        reset,
    input  logic [1:0]  resultsrc,
    input  logic [1:0]  pcsrc,
    input  logic [1:0]  srcasel,
    input  logic        alusrc,
    input  logic        regwrite,
    input  logic [2:0]  immsrc,
    input  logic [3:0]  alucontrol,
    output logic        zero,
    output logic        neg,
    output logic        ovf,
    output logic        carry,
    output logic [31:0] pc,
    input  logic [31:0] instr,
    output logic [31:0] aluresult,
    output logic [31:0] writedata,
    output logic [3:0]  byteen,
    input  logic [31:0] readword
);
    logic [31:0] pcnext, pcplus4, pctarget, jalrtarget;
    logic [31:0] immext;
    logic [31:0] rd1, rd2, srca, srcb;
    logic [31:0] loaddata, result;

    // Next PC
    flopr pcreg (.clk(clk), .reset(reset), .d(pcnext), .q(pc));
    adder32 pcadd4 (.a(pc), .b(32'd4), .cin(1'b0), .s(pcplus4), .cout());
    adder32 pcaddbranch (.a(pc), .b(immext), .cin(1'b0), .s(pctarget), .cout());
    assign jalrtarget = {aluresult[31:1], 1'b0};
    mux3 pcmux (.d0(pcplus4), .d1(pctarget), .d2(jalrtarget), .s(pcsrc), .y(pcnext));

    // Register file and immediates
    (* keep *)  // state element (black box): never optimised away
    regfile rf (
        .clk(clk), .we3(regwrite),
        .a1(instr[19:15]), .a2(instr[24:20]), .a3(instr[11:7]),
        .wd3(result), .rd1(rd1), .rd2(rd2)
    );
    extend ext (.instr(instr[31:7]), .immsrc(immsrc), .immext(immext));

    // ALU
    mux3 srcamux (.d0(rd1), .d1(pc), .d2(32'b0), .s(srcasel), .y(srca));
    mux2 srcbmux (.d0(rd2), .d1(immext), .s(alusrc), .y(srcb));
    alu alu (
        .a(srca), .b(srcb), .alucontrol(alucontrol), .result(aluresult),
        .zero(zero), .neg(neg), .ovf(ovf), .carry(carry)
    );

    // Memory access and write-back
    lsu lsu (
        .funct3(instr[14:12]), .offset(aluresult[1:0]), .storedata(rd2),
        .readword(readword), .writedata(writedata), .byteen(byteen),
        .loaddata(loaddata)
    );
    mux3 resultmux (.d0(aluresult), .d1(loaddata), .d2(pcplus4), .s(resultsrc), .y(result));
endmodule
