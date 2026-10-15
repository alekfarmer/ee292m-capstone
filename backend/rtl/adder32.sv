// 32-bit ripple-carry adder: a chain of 32 full adders.
// c[0] is the carry in, c[32] the carry out; bit 0 is the LSB.
(* keep_hierarchy *)
module adder32 (
    input  logic [31:0] a,
    input  logic [31:0] b,
    input  logic        cin,
    output logic [31:0] s,
    output logic        cout
);
    logic [32:0] c;

    assign c[0] = cin;
    assign cout = c[32];

    genvar i;
    generate
        for (i = 0; i < 32; i = i + 1) begin : g_bit
            full_adder fa (
                .a   (a[i]),
                .b   (b[i]),
                .cin (c[i]),
                .s   (s[i]),
                .cout(c[i+1])
            );
        end
    endgenerate
endmodule
