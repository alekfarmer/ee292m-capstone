// Extend the aligned load to 32 bits.
//
// funct3: 000 lb   001 lh   010 lw   100 lbu   101 lhu
// funct3[1:0] picks byte, halfword or word; funct3[2] = 1 means unsigned
// (fill with 0s), else the sign bit fills the upper bits.
module loadextend (
    input  logic [2:0]  funct3,
    input  logic [31:0] aligned,
    output logic [31:0] loaddata
);
    logic sign, byte_fill, half_fill;

    assign sign      = ~funct3[2];
    assign byte_fill = sign & aligned[7];
    assign half_fill = sign & aligned[15];

    mux3 pick (
        .d0({{24{byte_fill}}, aligned[7:0]}),
        .d1({{16{half_fill}}, aligned[15:0]}),
        .d2(aligned),
        .s(funct3[1:0]), .y(loaddata)
    );
endmodule
