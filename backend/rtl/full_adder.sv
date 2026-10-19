// One-bit full adder, written gate by gate so synthesis keeps the textbook
// structure: 2 XOR, 2 AND, 1 OR. The synthesis script excludes this module
// from ABC, so these five gates are exactly the gates that are drawn.
(* keep_hierarchy *)
module full_adder (
    input  logic a,
    input  logic b,
    input  logic cin,
    output logic s,
    output logic cout
);
    logic p;  // propagate: a XOR b
    logic g;  // generate:  a AND b
    logic t;  // carry propagated from cin: p AND cin

    assign p    = a ^ b;
    assign g    = a & b;
    assign s    = p ^ cin;
    assign t    = p & cin;
    assign cout = g | t;
endmodule
