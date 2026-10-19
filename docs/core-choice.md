# Core choice: our own single-cycle RV32I, after Harris & Harris

**Decision.** `backend/rtl/` is a single-cycle RV32I core written for this
project, MIT licensed (`backend/rtl/LICENSE`). Its structure and module names
follow the single-cycle processor in Harris & Harris, *Digital Design and
Computer Architecture, RISC-V Edition*, ch. 7 (`riscvsingle`, `controller`,
`maindec`, `aludec`, `datapath`, `alu`, `extend`, `regfile`), so it matches
what students see in the course.

**Why not the textbook code itself.** No openly licensed official copy of the
HDL was found; it ships with the (Elsevier) book. It also implements only
about ten instructions, while `sum.c` at `-O1` plus `crt0.S` need `lui`/`auipc`,
`jalr` and `bne`/`blt`, so it would have needed extending anyway.

**Differences from the textbook datapath.**
- Full RV32I base (no FENCE semantics, no CSRs, ECALL/EBREAK are no-ops).
- `srcasel` mux on ALU input A (rs1 / PC / 0) for `auipc` and `lui`.
- `pcsrc = 10` selects `(rs1 + imm) & ~1` for `jalr`.
- The ALU outputs zero/negative/overflow/carry flags; `branchunit` turns
  them into the six branch conditions.
- `lsu` handles byte and halfword loads and stores.
- A unified 4 KiB `ram` at `0x8000_0000` (Spike's default RAM base) instead of
  separate instruction and data memories.
- The ALU's adder is `adder32`, a structural chain of 32 `full_adder`
  modules, so the gate view is the textbook ripple-carry adder (see below).

**Why not CVA6, PicoRV32, SERV, ...** Pipelined, multicycle or bit-serial
cores break the "one instruction, one cycle" story the views tell, and are far
larger (CVA6 is application-class: MMU, caches, CSRs). Discussed in the M0
planning conversation, 2026-10-14.

**Keeping the adder readable.** `synth.ys` runs ABC on every module except
`full_adder`, so each bit is exactly 2 XOR + 2 AND + 1 OR. Without that
exclusion ABC is free to restructure the full adder (with MUX in the gate set
the carry can become `p ? cin : a`), and the picture would stop matching the
textbook.
