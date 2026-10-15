// Main decoder: opcode -> datapath control signals.
//
// immsrc:    000 I   001 S   010 B   011 J   100 U
// resultsrc: 00 ALU result   01 load data   10 PC + 4
// srcasel:   00 rs1          01 PC          10 zero
// aluop:     00 add          01 subtract (branch compare)   10 from funct3/funct7
// FENCE, ECALL, EBREAK and unknown opcodes are executed as no-ops.
module maindec (
    input  logic [6:0] op,
    output logic       regwrite,
    output logic [2:0] immsrc,
    output logic [1:0] srcasel,
    output logic       alusrc,
    output logic       memwrite,
    output logic [1:0] resultsrc,
    output logic       branch,
    output logic       jump,
    output logic       jumpreg,
    output logic [1:0] aluop
);
    always_comb begin
        // Defaults: a no-op.
        regwrite  = 1'b0;
        immsrc    = 3'b000;
        srcasel   = 2'b00;
        alusrc    = 1'b0;
        memwrite  = 1'b0;
        resultsrc = 2'b00;
        branch    = 1'b0;
        jump      = 1'b0;
        jumpreg   = 1'b0;
        aluop     = 2'b00;
        case (op)
            7'b0000011: begin  // loads
                regwrite = 1'b1; immsrc = 3'b000; alusrc = 1'b1; resultsrc = 2'b01;
            end
            7'b0100011: begin  // stores
                immsrc = 3'b001; alusrc = 1'b1; memwrite = 1'b1;
            end
            7'b0110011: begin  // R-type ALU
                regwrite = 1'b1; aluop = 2'b10;
            end
            7'b0010011: begin  // I-type ALU
                regwrite = 1'b1; immsrc = 3'b000; alusrc = 1'b1; aluop = 2'b10;
            end
            7'b1100011: begin  // branches
                immsrc = 3'b010; branch = 1'b1; aluop = 2'b01;
            end
            7'b1101111: begin  // jal
                regwrite = 1'b1; immsrc = 3'b011; resultsrc = 2'b10; jump = 1'b1;
            end
            7'b1100111: begin  // jalr: target = (rs1 + imm) & ~1 from the ALU
                regwrite = 1'b1; immsrc = 3'b000; alusrc = 1'b1; resultsrc = 2'b10;
                jumpreg = 1'b1;
            end
            7'b0110111: begin  // lui: 0 + imm
                regwrite = 1'b1; immsrc = 3'b100; srcasel = 2'b10; alusrc = 1'b1;
            end
            7'b0010111: begin  // auipc: PC + imm
                regwrite = 1'b1; immsrc = 3'b100; srcasel = 2'b01; alusrc = 1'b1;
            end
            default: ;
        endcase
    end
endmodule
