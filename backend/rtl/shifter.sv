// Barrel shifter: all three RV32I shifts of a by shamt, computed in parallel.
module shifter (
    input  logic [31:0] a,
    input  logic [4:0]  shamt,
    output logic [31:0] y_sll,
    output logic [31:0] y_srl,
    output logic [31:0] y_sra
);
    assign y_sll = a << shamt;
    assign y_srl = a >> shamt;
    assign y_sra = $signed(a) >>> shamt;
endmodule
