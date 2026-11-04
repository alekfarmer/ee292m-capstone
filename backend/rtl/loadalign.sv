// Move the addressed byte or halfword down to bit 0: shift the memory word
// right by `offset` bytes, in two stages of 2:1 multiplexers (8, then 16).
module loadalign (
    input  logic [1:0]  offset,
    input  logic [31:0] readword,
    output logic [31:0] aligned
);
    logic [31:0] by8;

    mux2 m_by8  (.d0(readword), .d1({8'b0,  readword[31:8]}), .s(offset[0]), .y(by8));
    mux2 m_by16 (.d0(by8),      .d1({16'b0, by8[31:16]}),     .s(offset[1]), .y(aligned));
endmodule
