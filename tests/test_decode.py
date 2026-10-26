"""Instruction words split into the right fields and immediates."""

import itertools
from pathlib import Path

import pytest

from app import pipeline
from app.decode import decode


@pytest.mark.parametrize(
    ("word", "fmt", "imm", "meanings"),
    [
        (
            0x00000513,
            "I",
            0,
            ["immediate = 0", "rs1 = x0 (zero)", "rd = x10 (a0)"],
        ),  # addi a0,zero,0
        (
            0x00B50533,
            "R",
            None,
            ["rs2 = x11 (a1)", "rs1 = x10 (a0)", "rd = x10 (a0)"],
        ),  # add a0,a0,a1
        (0x03700513, "I", 55, ["immediate = 55"]),  # addi a0,zero,55
        (
            0xFEF75AE3,
            "B",
            -12,
            ["rs2 = x15 (a5)", "rs1 = x14 (a4)", "funct3 = bge"],
        ),  # bge a4,a5,-12
        (0x0062A023, "S", 0, ["rs2 = x6 (t1)", "rs1 = x5 (t0)", "funct3 = sw"]),  # sw t1,0(t0)
        (0x00001117, "U", 0x1000, ["rd = x2 (sp)"]),  # auipc sp,0x1
        (0x01C000EF, "J", 28, ["rd = x1 (ra)", "offset = 28"]),  # jal ra,+28
        (0x00151313, "I", 1, ["shamt = 1", "funct3 = slli"]),  # slli t1,a0,1
        (0xFFF00513, "I", -1, ["immediate = -1"]),  # addi a0,zero,-1
    ],
)
def test_known_encodings(word: int, fmt: str, imm: int | None, meanings: list[str]) -> None:
    dec = decode(word)
    assert dec.format == fmt
    assert dec.immediate == imm
    shown = [f.meaning for f in dec.fields]
    for m in meanings:
        assert m in shown, (m, shown)


@pytest.mark.parametrize("word", [0x00000513, 0x00B50533, 0xFEF75AE3, 0x0062A023, 0x01C000EF, 0x0])
def test_fields_cover_every_bit_once_and_reassemble(word: int) -> None:
    fields = decode(word).fields
    assert [(f.hi, f.lo) for f in fields] == sorted(((f.hi, f.lo) for f in fields), reverse=True)
    assert fields[0].hi == 31 and fields[-1].lo == 0
    for a, b in itertools.pairwise(fields):
        assert a.lo == b.hi + 1, "fields must be contiguous"
    assert int("".join(f.bits for f in fields), 2) == word


def test_program_listing_fields_match_hex(fresh_dir: Path) -> None:
    for line in pipeline.get_program(fresh_dir).asm:
        assert int("".join(f.bits for f in line.fields), 2) == int(line.hex, 16), line.addr
        assert line.format is not None, f"{line.addr} {line.text} not decoded"
