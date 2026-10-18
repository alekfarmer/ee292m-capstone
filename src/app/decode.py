"""Split RV32I instruction words into their encoding fields.

Each instruction format (R, I, S, B, U, J) lays out the 32 bits differently.
:func:`decode` returns every field with its bit range, its bits and what it
means, plus the instruction's immediate value (sign-extended), so the page
can colour the binary without decoding anything itself.
"""

from dataclasses import dataclass
from typing import Literal

Format = Literal["R", "I", "S", "B", "U", "J"]

ABI_NAMES = [
    "zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
    "s0", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
    "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
    "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6",
]  # fmt: skip

OPCODES: dict[int, tuple[str, Format]] = {
    0b0110011: ("OP: register-register ALU", "R"),
    0b0010011: ("OP-IMM: register-immediate ALU", "I"),
    0b0000011: ("LOAD", "I"),
    0b0100011: ("STORE", "S"),
    0b1100011: ("BRANCH", "B"),
    0b1101111: ("JAL: jump and link", "J"),
    0b1100111: ("JALR: jump and link register", "I"),
    0b0110111: ("LUI: load upper immediate", "U"),
    0b0010111: ("AUIPC: add upper immediate to PC", "U"),
    0b0001111: ("MISC-MEM: fence", "I"),
    0b1110011: ("SYSTEM: ecall / ebreak", "I"),
}

FUNCT3: dict[int, dict[int, str]] = {
    0b0110011: {
        0: "add/sub", 1: "sll", 2: "slt", 3: "sltu",
        4: "xor", 5: "srl/sra", 6: "or", 7: "and",
    },
    0b0010011: {
        0: "addi", 1: "slli", 2: "slti", 3: "sltiu",
        4: "xori", 5: "srli/srai", 6: "ori", 7: "andi",
    },
    0b0000011: {0: "lb", 1: "lh", 2: "lw", 4: "lbu", 5: "lhu"},
    0b0100011: {0: "sb", 1: "sh", 2: "sw"},
    0b1100011: {0: "beq", 1: "bne", 4: "blt", 5: "bge", 6: "bltu", 7: "bgeu"},
    0b1100111: {0: "jalr"},
}  # fmt: skip


@dataclass(frozen=True)
class Field:
    """One encoding field: bits ``hi`` down to ``lo`` of the instruction."""

    name: str
    hi: int
    lo: int
    bits: str  # MSB first
    meaning: str


@dataclass(frozen=True)
class Decoded:
    """An instruction's format, fields (MSB first) and immediate."""

    format: Format | None
    opcode_name: str
    fields: list[Field]
    immediate: int | None


def bits_of(word: int, hi: int, lo: int) -> int:
    """Bits ``hi..lo`` of ``word`` as an unsigned integer."""
    return (word >> lo) & ((1 << (hi - lo + 1)) - 1)


def sign_extend(value: int, width: int) -> int:
    """Interpret the low ``width`` bits of ``value`` as two's complement."""
    value &= (1 << width) - 1
    return value - (1 << width) if value >> (width - 1) else value


def _reg(word: int, hi: int, lo: int, role: str) -> Field:
    n = bits_of(word, hi, lo)
    return _field(word, role, hi, lo, f"{role} = x{n} ({ABI_NAMES[n]})")


def _field(word: int, name: str, hi: int, lo: int, meaning: str) -> Field:
    return Field(name, hi, lo, format(bits_of(word, hi, lo), f"0{hi - lo + 1}b"), meaning)


def immediate(word: int, fmt: Format) -> int | None:
    """The sign-extended immediate of ``word`` in format ``fmt`` (None for R)."""
    if fmt == "I":
        return sign_extend(bits_of(word, 31, 20), 12)
    if fmt == "S":
        return sign_extend((bits_of(word, 31, 25) << 5) | bits_of(word, 11, 7), 12)
    if fmt == "B":
        raw = (
            (bits_of(word, 31, 31) << 12)
            | (bits_of(word, 7, 7) << 11)
            | (bits_of(word, 30, 25) << 5)
            | (bits_of(word, 11, 8) << 1)
        )
        return sign_extend(raw, 13)
    if fmt == "U":
        return sign_extend(bits_of(word, 31, 12) << 12, 32)
    if fmt == "J":
        raw = (
            (bits_of(word, 31, 31) << 20)
            | (bits_of(word, 19, 12) << 12)
            | (bits_of(word, 20, 20) << 11)
            | (bits_of(word, 30, 21) << 1)
        )
        return sign_extend(raw, 21)
    return None


def decode(word: int) -> Decoded:
    """Split ``word`` into the fields of its format (MSB first)."""
    op = bits_of(word, 6, 0)
    name, fmt = OPCODES.get(op, ("unknown opcode", None))
    f3 = bits_of(word, 14, 12)
    f3_name = FUNCT3.get(op, {}).get(f3, "")
    opcode = _field(word, "opcode", 6, 0, f"opcode = {name}")
    funct3 = _field(word, "funct3", 14, 12, f"funct3 = {f3_name}" if f3_name else "funct3")
    imm = immediate(word, fmt) if fmt else None

    if fmt == "R":
        f7 = bits_of(word, 31, 25)
        f7_meaning = "funct7 = sub/sra" if f7 == 0b0100000 else "funct7"
        fields = [
            _field(word, "funct7", 31, 25, f7_meaning),
            _reg(word, 24, 20, "rs2"),
            _reg(word, 19, 15, "rs1"),
            funct3,
            _reg(word, 11, 7, "rd"),
            opcode,
        ]
    elif fmt == "I" and op == 0b0010011 and f3 in (1, 5):  # shifts: funct7 + shamt
        shamt = bits_of(word, 24, 20)
        f7 = bits_of(word, 31, 25)
        fields = [
            _field(word, "funct7", 31, 25, "funct7 = srai" if f7 == 0b0100000 else "funct7"),
            _field(word, "shamt", 24, 20, f"shamt = {shamt}"),
            _reg(word, 19, 15, "rs1"),
            funct3,
            _reg(word, 11, 7, "rd"),
            opcode,
        ]
        imm = shamt
    elif fmt == "I":
        fields = [
            _field(word, "imm[11:0]", 31, 20, f"immediate = {imm}"),
            _reg(word, 19, 15, "rs1"),
            funct3,
            _reg(word, 11, 7, "rd"),
            opcode,
        ]
    elif fmt == "S":
        fields = [
            _field(word, "imm[11:5]", 31, 25, f"immediate bits [11:5] (immediate = {imm})"),
            _reg(word, 24, 20, "rs2"),
            _reg(word, 19, 15, "rs1"),
            funct3,
            _field(word, "imm[4:0]", 11, 7, "immediate bits [4:0]"),
            opcode,
        ]
    elif fmt == "B":
        fields = [
            _field(word, "imm[12|10:5]", 31, 25, f"offset bits 12, 10:5 (offset = {imm})"),
            _reg(word, 24, 20, "rs2"),
            _reg(word, 19, 15, "rs1"),
            funct3,
            _field(word, "imm[4:1|11]", 11, 7, "offset bits 4:1, 11"),
            opcode,
        ]
    elif fmt == "U":
        fields = [
            _field(word, "imm[31:12]", 31, 12, f"upper immediate = 0x{bits_of(word, 31, 12):05x}"),
            _reg(word, 11, 7, "rd"),
            opcode,
        ]
    elif fmt == "J":
        fields = [
            _field(word, "imm[20|10:1|11|19:12]", 31, 12, f"offset = {imm}"),
            _reg(word, 11, 7, "rd"),
            opcode,
        ]
    else:
        fields = [_field(word, "bits", 31, 7, "not decoded"), opcode]
    return Decoded(format=fmt, opcode_name=name, fields=fields, immediate=imm)
