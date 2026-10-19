// ALU decoder: aluop, funct3 and funct7 bit 5 -> alucontrol (see alu.sv).
module aludec (
    input  logic       opb5,      // instr[5]: 1 for R-type, 0 for I-type
    input  logic [2:0] funct3,
    input  logic       funct7b5,  // instr[30]
    input  logic [1:0] aluop,
    output logic [3:0] alucontrol
);
    always_comb begin
        case (aluop)
            2'b00:   alucontrol = 4'b0000;  // add
            2'b01:   alucontrol = 4'b0001;  // sub (branch compare)
            default: begin
                case (funct3)
                    3'b000:  alucontrol = (opb5 & funct7b5) ? 4'b0001 : 4'b0000;  // sub : add
                    3'b001:  alucontrol = 4'b0111;                               // sll
                    3'b010:  alucontrol = 4'b0101;                               // slt
                    3'b011:  alucontrol = 4'b0110;                               // sltu
                    3'b100:  alucontrol = 4'b0100;                               // xor
                    3'b101:  alucontrol = funct7b5 ? 4'b1001 : 4'b1000;          // sra : srl
                    3'b110:  alucontrol = 4'b0011;                               // or
                    default: alucontrol = 4'b0010;                               // and
                endcase
            end
        endcase
    end
endmodule
