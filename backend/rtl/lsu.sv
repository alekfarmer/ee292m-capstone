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
    logic [7:0]  rbyte;
    logic [15:0] rhalf;

    always_comb begin
        case (funct3[1:0])
            2'b00: begin
                writedata = {4{storedata[7:0]}};
                byteen    = 4'b0001 << offset;
            end
            2'b01: begin
                writedata = {2{storedata[15:0]}};
                byteen    = offset[1] ? 4'b1100 : 4'b0011;
            end
            default: begin
                writedata = storedata;
                byteen    = 4'b1111;
            end
        endcase
    end

    always_comb begin
        case (offset)
            2'b00:   rbyte = readword[7:0];
            2'b01:   rbyte = readword[15:8];
            2'b10:   rbyte = readword[23:16];
            default: rbyte = readword[31:24];
        endcase
        rhalf = offset[1] ? readword[31:16] : readword[15:0];

        case (funct3)
            3'b000:  loaddata = {{24{rbyte[7]}}, rbyte};
            3'b001:  loaddata = {{16{rhalf[15]}}, rhalf};
            3'b100:  loaddata = {24'b0, rbyte};
            3'b101:  loaddata = {16'b0, rhalf};
            default: loaddata = readword;
        endcase
    end
endmodule
