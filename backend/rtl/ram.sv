// Unified instruction/data memory: 4 KiB at 0x8000_0000, 1024 words.
// Instruction port and data port read combinationally; the data port writes
// the enabled byte lanes on the rising clock edge. Addresses outside the RAM
// wrap (only bits [11:2] are used).
// Synthesis keeps this module as a black box (see synth.ys).
module ram (
    input  logic        clk,
    input  logic [31:0] iaddr,
    output logic [31:0] idata,
    input  logic [31:0] daddr,
    input  logic        dwe,
    input  logic [3:0]  dbe,
    input  logic [31:0] dwdata,
    output logic [31:0] drdata
);
    logic [31:0] mem [0:1023];

    assign idata  = mem[iaddr[11:2]];
    assign drdata = mem[daddr[11:2]];

    always_ff @(posedge clk) begin
        if (dwe) begin
            if (dbe[0]) mem[daddr[11:2]][7:0]   <= dwdata[7:0];
            if (dbe[1]) mem[daddr[11:2]][15:8]  <= dwdata[15:8];
            if (dbe[2]) mem[daddr[11:2]][23:16] <= dwdata[23:16];
            if (dbe[3]) mem[daddr[11:2]][31:24] <= dwdata[31:24];
        end
    end
endmodule
