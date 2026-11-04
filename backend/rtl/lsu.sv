// Load/store alignment for byte, halfword and word accesses on a
// little-endian 32-bit memory. Accesses are assumed naturally aligned.
//
// funct3: 000 b   001 h   010 w   100 bu   101 hu
module lsu (
    input  logic [2:0]  funct3,
    input  logic [1:0]  offset,     // address bits [1:0]
    input  logic [31:0] storedata,  // rs2
    input  logic [31:0] readword,   // the addressed memory word
    output logic [31:0] writedata,  // store data placed in its byte lanes
    output logic [3:0]  byteen,     // byte lanes written
    output logic [31:0] loaddata    // load result, extended to 32 bits
);
    logic [31:0] aligned;

    storealign st (
        .size(funct3[1:0]), .offset(offset), .storedata(storedata),
        .writedata(writedata), .byteen(byteen)
    );
    loadalign  la (.offset(offset), .readword(readword), .aligned(aligned));
    loadextend lx (.funct3(funct3), .aligned(aligned), .loaddata(loaddata));
endmodule
