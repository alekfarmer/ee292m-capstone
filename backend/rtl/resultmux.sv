// ALU result select: picks one unit's output by alucontrol (see alu.sv).
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
    always_comb begin
        case (alucontrol)
            4'b0000: result = sum;
            4'b0001: result = sum;
            4'b0010: result = y_and;
            4'b0011: result = y_or;
            4'b0100: result = y_xor;
            4'b0101: result = {31'b0, lt};
            4'b0110: result = {31'b0, ltu};
            4'b0111: result = y_sll;
            4'b1000: result = y_srl;
            4'b1001: result = y_sra;
            default: result = 32'b0;
        endcase
    end
endmodule
