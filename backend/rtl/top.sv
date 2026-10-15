// Top level: the processor and its unified memory.
module top (
    input logic clk,
    input logic reset
);
    logic [31:0] pc, instr, daddr, writedata, readword;
    logic [3:0]  byteen;
    logic        memwrite;

    riscvsingle rv (
        .clk(clk), .reset(reset), .pc(pc), .instr(instr),
        .memwrite(memwrite), .byteen(byteen), .aluresult(daddr),
        .writedata(writedata), .readword(readword)
    );

    // keep: the top level has no outputs, so without it synthesis would see
    // the memory (and so the whole core) as driving nothing and remove it.
    (* keep *)
    ram mem (
        .clk(clk), .iaddr(pc), .idata(instr),
        .daddr(daddr), .dwe(memwrite), .dbe(byteen),
        .dwdata(writedata), .drdata(readword)
    );
endmodule
