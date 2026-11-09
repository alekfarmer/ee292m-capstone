"""The committed programs together run every RV32I instruction the core has.

Spike checks each retired instruction's register write, so a decoder fault
(sltu decoded as slt, say) is caught only if some program runs that
instruction with operands where the right and wrong answers differ. sum.c
alone runs eight kinds of instruction; this test keeps the examples covering
all of them.
"""

from pathlib import Path

from app import pipeline

# RV32I, from the specification (unprivileged ISA, chapter 2), less the
# instructions this core does not implement (fence, ecall, ebreak).
RV32I = {
    "lui", "auipc", "jal", "jalr",
    "beq", "bne", "blt", "bge", "bltu", "bgeu",
    "lb", "lh", "lw", "lbu", "lhu", "sb", "sh", "sw",
    "addi", "slti", "sltiu", "xori", "ori", "andi", "slli", "srli", "srai",
    "add", "sub", "sll", "slt", "sltu", "xor", "srl", "sra", "or", "and",
}  # fmt: skip


def executed(art_dir: Path, program: str) -> set[str]:
    """The mnemonics of every instruction the program retires in Spike."""
    listing = pipeline.get_program(art_dir, program)
    text = {int(a.addr, 16): a.text for a in listing.asm}
    golden = pipeline.get_golden(art_dir, program)
    return {text[int(e.pc, 16)].split()[0] for e in golden.entries}


def test_the_examples_run_every_rv32i_instruction(fresh_dir: Path) -> None:
    seen: set[str] = set()
    for program in pipeline.list_programs(fresh_dir):
        seen |= executed(fresh_dir, program)
    missing = sorted(RV32I - seen)
    assert not missing, f"no committed program runs: {', '.join(missing)}"
