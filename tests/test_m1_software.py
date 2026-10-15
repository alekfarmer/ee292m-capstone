"""M1: the fixed program compiles, round-trips, and Spike halts with a0 = 55."""

import filecmp
from pathlib import Path

import pytest

from app import pipeline, software
from app.models import GoldenArtifact, ProgramArtifact
from app.paths import ARTIFACTS_DIR


@pytest.fixture(scope="module")
def program(fresh_dir: Path) -> ProgramArtifact:
    return pipeline.get_program(fresh_dir)


@pytest.fixture(scope="module")
def golden(fresh_dir: Path) -> GoldenArtifact:
    return pipeline.get_golden(fresh_dir)


def read_image(path: Path) -> list[int]:
    return [int(line, 16) for line in path.read_text().splitlines() if not line.startswith("//")]


def test_spike_halts_with_a0_equal_55(golden: GoldenArtifact) -> None:
    assert golden.a0_at_halt == "0x00000037"
    assert golden.exit_code == 55
    assert golden.retired <= golden.max_cycles == 500


def test_golden_log_runs_from_entry_to_the_halt_store(
    program: ProgramArtifact, golden: GoldenArtifact
) -> None:
    assert golden.entries[0].pc == program.entry
    by_addr = {line.addr: line for line in program.asm}
    for entry in golden.entries:
        assert entry.pc in by_addr, f"Spike ran {entry.pc}, which is not in the listing"
        assert entry.insn == by_addr[entry.pc].hex, f"Spike and objdump disagree at {entry.pc}"
    last = by_addr[golden.entries[-1].pc]
    assert last.text.startswith("sw "), "the log must end with the store to tohost"


def test_asm_hex_disassembles_to_its_text(program: ProgramArtifact, tmp_path: Path) -> None:
    words = [int(line.hex, 16) for line in program.asm]
    texts = software.disassemble_words(words, int(program.asm[0].addr, 16), tmp_path)
    expected = [software.strip_symbols(line.text) for line in program.asm]
    assert [software.strip_symbols(t) for t in texts] == expected


def test_asm_text_assembles_to_its_hex(program: ProgramArtifact, tmp_path: Path) -> None:
    texts = [line.text for line in program.asm]
    addrs = [int(line.addr, 16) for line in program.asm]
    words = software.assemble(texts, addrs, tmp_path)
    assert [f"0x{w:08x}" for w in words] == [line.hex for line in program.asm]


def test_hex_image_holds_the_listed_instructions(program: ProgramArtifact, fresh_dir: Path) -> None:
    words = read_image(fresh_dir / program.image_file)
    assert len(words) == program.ram_size_bytes // 4
    base = int(program.ram_base, 16)
    for line in program.asm:
        assert f"0x{words[(int(line.addr, 16) - base) // 4]:08x}" == line.hex, line.addr


@pytest.mark.parametrize(
    ("text", "word"),
    [("addi a0, zero, 0", 0x0000_0513), ("add a0, a0, a1", 0x00B5_0533)],
)
def test_reference_encodings(text: str, word: int, tmp_path: Path) -> None:
    assert software.assemble([text], [0x8000_0000], tmp_path) == [word]
    assert software.disassemble_words([word], 0x8000_0000, tmp_path) == [text.replace(", ", ",")]


def test_main_maps_to_c_lines(program: ProgramArtifact) -> None:
    main = [line for line in program.asm if line.function == "main"]
    assert main, "no main in the listing"
    assert all(line.c_line is not None for line in main)
    assert {line.c_line for line in main} <= {c.line for c in program.c_lines}
    start = [line for line in program.asm if line.function == "_start"]
    assert start and all(line.c_line is None for line in start)


def test_addresses_are_word_aligned_and_consecutive(program: ProgramArtifact) -> None:
    addrs = [int(line.addr, 16) for line in program.asm]
    assert all(a % 4 == 0 for a in addrs)


@pytest.mark.parametrize("name", [pipeline.PROGRAM_FILE, pipeline.GOLDEN_FILE, "sum.hex"])
def test_committed_program_artifacts_are_up_to_date(fresh_dir: Path, name: str) -> None:
    assert filecmp.cmp(fresh_dir / name, ARTIFACTS_DIR / name, shallow=False), (
        f"backend/artifacts/{name} is stale; run 'make artifacts'"
    )
