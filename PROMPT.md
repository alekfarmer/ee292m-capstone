# Prompt

Follow AGENTS.md. Read `README.md` for the architecture and milestones. This prompt covers **M0 and M1 only**.

## 1) Context

I am building a browser-based visualization that follows one C program from
source to RISC-V assembly to machine code to a running processor datapath, and
down to logic gates, with real values at every cycle. Users: Students interested in the whole stack from SW to HW. So **correctness of every displayed bit matters more than visual
polish.**

## 2) Scope

**This task (riskiest first):**

- **M0, gate-level spike:** Synthesize the RV32I core (see Method) with Yosys,
  keeping hierarchy. Report gate counts per module. Produce a minimal static
  HTML page that renders *only the ALU's adder* at gate level, with values
  from a 32-bit `5 + 3` add.

- **M1, software pipeline:** Compile the fixed program below to RV32I. Emit the
  asm listing, hex image, and Spike golden commit log from one command
  (`make artifacts` or similar).

**Not now:** user-entered C, pipelining, caches, M/F/C extensions, CSRs and
interrupts, libc/printf, a polished UI, a full-core gate view.

**First step:** Before writing code, tell me which core you chose and why
(two or three sentences), its license, and the exact tool versions you'll pin.
Then do M0.

## 3) Data

**Input: fixed program `backend/programs/sum.c`**

```c
int main(void) {
    int sum = 0;
    for (int i = 1; i <= 10; i++)
        sum += i;
    return sum;   // expected: 55 in a0
}
```

Allowed C subset (for later): `int` (32-bit signed two's complement), `+ - & |
^ << >>`, comparisons, `if/for/while`, local variables, and small global arrays
of 256 words or fewer. No floats, `*` / `/` (no M extension), pointers to
functions, libc, or I/O.

**Outputs** (JSON in `backend/artifacts/`, consumed by the frontend):
| Artifact | Contents | Units / range |
|---|---|---|
| `program.json` | C lines; asm lines `{addr, hex, text, c_line}` | addr: byte address, 4-aligned; hex: 32-bit word |
| `golden.json` | Spike commit log: `{pc, insn, rd, rd_value}` per retired instruction | values: uint32 as `0x%08x` |
| `netlist.json` | Yosys JSON, hierarchy preserved, gates in {AND, OR, XOR, NOT, MUX, DFF} | ~10³–10⁴ cells (report the actual count) |
| `trace.json` (M2) | net value changes per cycle | cycles: 0–500; bit order `[31:0]`, LSB = bit 0 |

**Real rows** to sanity-check encoding (RV32I, little-endian):
| asm | hex |
|---|---|
| `addi a0, zero, 0` | `0x00000513` |
| `add a0, a0, a1` | `0x00b50533` |

## 4) Method

- **Toolchain:** `riscv64-unknown-elf-gcc -march=rv32i -mabi=ilp32 -O1 -g
  -nostdlib -ffreestanding`, with a minimal `crt0.S` (set `sp`, call `main`,
  then halt) and a linker script.
- **Asm and C mapping:** `riscv64-unknown-elf-objdump -d -l` (DWARF line info).
- **Golden model:** Spike (`riscv-isa-sim`), `--isa=rv32i --log-commits`.
- **Core:** a single-cycle RV32I teaching core in SystemVerilog, preferably the
  Harris & Harris *DDCA RISC-V Edition* design (or propose an alternative with
  justification; avoid multicycle or bit-serial cores for M0).
- **Synthesis:** Yosys. Do not `flatten`; map to the gate set above
  (`techmap` + `abc -g AND,OR,XOR,MUX` or equivalent). Keep the register file
  and memories as black boxes. If ABC makes the adder unrecognizable, say so
  and propose a structural ripple-carry ALU instead.
- **Rendering for M0:** netlistsvg or plain SVG. No framework required yet.
- Pin all tool versions (Dockerfile or Nix). Commit generated artifacts.

## 5) Truths

**Checks that must pass (as automated tests):**
- Spike: `a0 == 55` at halt.
- Every asm line in `program.json` round-trips: hex ↔ objdump text.
- The two encoding rows above appear exactly as listed when assembled.
- M0: the rendered adder's sum bits read `0x00000008` for inputs 5 and 3, and
  carry-out = 0; also test `0xFFFFFFFF + 1 = 0` with carry-out = 1.
- Gate-count report exists and lists ALU, decoder, control, and top-level
  counts separately.
- (M2, later) register writes match `golden.json` for every retired
  instruction; gate-level sim equals RTL sim bit-for-bit every cycle;
  `x0 == 0` always.

**Inputs the pipeline must reject with a clear error (not crash or silently
miscompile):** floats; `*`, `/`, `%`; calls into libc; programs whose image
exceeds RAM; programs that don't halt within 500 cycles.

**Report back:** core choice and license, tool versions, gate counts, test
results, and anything that contradicts this plan.
