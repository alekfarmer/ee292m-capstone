// Control unit: main decoder, ALU decoder and branch condition.
//
// pcsrc: 00 PC + 4   01 PC + imm (jal, taken branch)   10 ALU result (jalr)
module controller (
    input  logic [6:0] op,
    input  logic [2:0] funct3,
    input  logic       funct7b5,
    input  logic       zero,
    input  logic       neg,
    input  logic       ovf,
    input  logic       carry,
    output logic [1:0] resultsrc,
    output logic       memwrite,
    output logic [1:0] pcsrc,
    output logic [1:0] srcasel,
    output logic       alusrc,
    output logic       regwrite,
    output logic [2:0] immsrc,
    output logic [3:0] alucontrol
);
    logic [1:0] aluop;
    logic       branch;
    logic       jump;
    logic       jumpreg;
    logic       taken;

    maindec md (
        .op       (op),
        .regwrite (regwrite),
        .immsrc   (immsrc),
        .srcasel  (srcasel),
        .alusrc   (alusrc),
        .memwrite (memwrite),
        .resultsrc(resultsrc),
        .branch   (branch),
        .jump     (jump),
        .jumpreg  (jumpreg),
        .aluop    (aluop)
    );

    aludec ad (
        .opb5      (op[5]),
        .funct3    (funct3),
        .funct7b5  (funct7b5),
        .aluop     (aluop),
        .alucontrol(alucontrol)
    );

    branchunit bu (
        .funct3(funct3),
        .zero  (zero),
        .neg   (neg),
        .ovf   (ovf),
        .carry (carry),
        .taken (taken)
    );

    assign pcsrc = jumpreg ? 2'b10 : ((jump | (branch & taken)) ? 2'b01 : 2'b00);
endmodule
