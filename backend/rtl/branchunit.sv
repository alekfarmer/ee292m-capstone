// Branch condition from the ALU flags of rs1 - rs2, selected by funct3.
module branchunit (
    input  logic [2:0] funct3,
    input  logic       zero,
    input  logic       neg,
    input  logic       ovf,
    input  logic       carry,
    output logic       taken
);
    always_comb begin
        case (funct3)
            3'b000:  taken = zero;          // beq
            3'b001:  taken = ~zero;         // bne
            3'b100:  taken = neg ^ ovf;     // blt
            3'b101:  taken = ~(neg ^ ovf);  // bge
            3'b110:  taken = ~carry;        // bltu
            3'b111:  taken = carry;         // bgeu
            default: taken = 1'b0;
        endcase
    end
endmodule
