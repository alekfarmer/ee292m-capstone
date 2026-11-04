// Store data in its byte lanes, and which lanes to write.
//
// size (funct3[1:0]): 00 byte   01 halfword   1x word
// A byte or halfword is copied into every lane it could go to; byteen picks
// the lane(s) the address selects.
module storealign (
    input  logic [1:0]  size,
    input  logic [1:0]  offset,
    input  logic [31:0] storedata,
    output logic [31:0] writedata,
    output logic [3:0]  byteen
);
    mux3 lanes (
        .d0({4{storedata[7:0]}}), .d1({2{storedata[15:0]}}), .d2(storedata),
        .s(size), .y(writedata)
    );

    always_comb begin
        case (size)
            2'b00:   byteen = 4'b0001 << offset;
            2'b01:   byteen = offset[1] ? 4'b1100 : 4'b0011;
            default: byteen = 4'b1111;
        endcase
    end
endmodule
