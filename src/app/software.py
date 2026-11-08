"""M1 software pipeline: C -> RV32I ELF -> asm listing, hex image, Spike log.

Every step calls the pinned toolchain (gcc, binutils, Spike) installed in the
image. Programs outside the supported C subset are rejected with a
:class:`~app.errors.ProgramRejectedError` carrying one plain message.
"""

import itertools
import re
from dataclasses import dataclass
from pathlib import Path

from app.decode import decode
from app.errors import ProgramRejectedError, ToolError
from app.models import AsmLine, GoldenArtifact, GoldenEntry, InstructionField
from app.paths import CRT0, LINKER_SCRIPT
from app.tools import ToolStream, run_tool

GCC = "riscv64-unknown-elf-gcc"
AS = "riscv64-unknown-elf-as"
LD = "riscv64-unknown-elf-ld"
OBJDUMP = "riscv64-unknown-elf-objdump"
OBJCOPY = "riscv64-unknown-elf-objcopy"
NM = "riscv64-unknown-elf-nm"
SPIKE = "spike"

MARCH = ["-march=rv32i", "-mabi=ilp32"]
COMPILE_FLAGS = [*MARCH, "-Og", "-g", "-nostdlib", "-ffreestanding"]
RAM_BASE = 0x8000_0000
RAM_SIZE = 4096  # bytes; must match link.ld and backend/rtl/ram.sv
MAX_CYCLES = 500  # single-cycle core: one retired instruction per cycle
SPIKE_ISA = "rv32i"
SPIKE_WALL_TIMEOUT_S = 30.0

# Helper routines GCC calls for operations RV32I has no instruction for.
_HELPER_REASONS = {
    "__mulsi3": "multiplication ('*') needs the M extension, which the core does not have",
    "__divsi3": "division ('/') needs the M extension, which the core does not have",
    "__udivsi3": "division ('/') needs the M extension, which the core does not have",
    "__modsi3": "remainder ('%') needs the M extension, which the core does not have",
    "__umodsi3": "remainder ('%') needs the M extension, which the core does not have",
}
_FLOAT_HELPER = re.compile(r"^__\w*(sf|df|tf)\w*$")


@dataclass(frozen=True)
class CompiledProgram:
    """A linked program and the facts later steps need about it."""

    elf: Path
    source_name: str
    entry: int
    tohost: int


# --- subset check -------------------------------------------------------------

_LINEMARKER = re.compile(r'^# (\d+) "(.*)"')
_STRING_OR_CHAR = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
_FLOAT_KEYWORD = re.compile(r"\b(float|double)\b")
_FLOAT_LITERAL = re.compile(
    r"(?<![\w.])(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?[fFlL]?(?![\w.])"
    r"|(?<![\w.])\d+[eE][+-]?\d+[fFlL]?(?![\w.])"
)
_OPERATORS = {
    "*": "'*' is not supported: the core has no M extension (and pointers are outside the subset)",
    "/": "'/' is not supported: the core has no M extension",
    "%": "'%' is not supported: the core has no M extension",
}


# Text that makes the preprocessor act: '#' starts a directive (#include
# reads a file), and '%:' and '??=' are other spellings of '#'.
_DIRECTIVE_SPELLINGS = {
    "#": "'#' is not supported: the subset has no preprocessor directives "
    "(#include, #define, ...), and '#' is refused anywhere, comments included",
    "%:": "'%:' is not supported: it is another spelling of '#', and the subset "
    "has no preprocessor directives",
    "??=": "'??=' is not supported: it is another spelling of '#', and the subset "
    "has no preprocessor directives",
}
# Keywords that hand text to the assembler or the preprocessor
# (`.incbin` would copy a file into the program).
_INLINE_ASM = re.compile(r"\b(asm|__asm|__asm__)\b")
_PRAGMA_OPERATOR = re.compile(r"\b_Pragma\b")


def _code_only(text: str) -> str:
    """``text`` with line splices joined and comments, strings and characters blanked.

    Follows C's translation phases 2 and 3: a backslash-newline joins two
    lines (inside an identifier too), then comments become a space and
    string and character literals become empty quotes. Line breaks outside
    splices are kept, so a line number in the result is the one in ``text``
    unless a splice came before it (then it is early by one per splice).
    """
    text = text.replace("\\\r\n", "").replace("\\\n", "")
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        two = text[i : i + 2]
        if two == "//":
            end = text.find("\n", i)
            i = n if end < 0 else end
            out.append(" ")
        elif two == "/*":
            end = text.find("*/", i + 2)
            comment = text[i : n if end < 0 else end + 2]
            out.append(" " + "\n" * comment.count("\n"))
            i = n if end < 0 else end + 2
        elif ch in "\"'":
            j = i + 1
            while j < n and text[j] != ch and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            out.append(ch + ch)
            i = j + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def check_source_text(text: str, name: str) -> None:
    """Refuse source that could make the compiler read anything but itself.

    Runs before any tool sees the source: the subset check's preprocessor
    would otherwise follow an ``#include`` of any file in the container, and
    gcc's errors quote what it read. Refused: ``#`` and its other spellings
    anywhere, inline assembly (``asm``, ``__asm__``), and ``_Pragma``.

    Raises:
        ProgramRejectedError: with the file, line and reason of the first problem.
    """
    for spelling, reason in _DIRECTIVE_SPELLINGS.items():
        if (at := text.find(spelling)) >= 0:
            raise ProgramRejectedError(f"{name}:{text.count(chr(10), 0, at) + 1}: {reason}")
    code = _code_only(text)
    if m := _INLINE_ASM.search(code):
        raise ProgramRejectedError(
            f"{name}:{code.count(chr(10), 0, m.start()) + 1}: inline assembly "
            f"('{m.group(1)}') is not supported: the program is C only"
        )
    if m := _PRAGMA_OPERATOR.search(code):
        raise ProgramRejectedError(
            f"{name}:{code.count(chr(10), 0, m.start()) + 1}: _Pragma is not "
            "supported: the subset has no preprocessor"
        )


def check_subset(c_file: Path) -> None:
    """Reject C constructs outside the supported subset, before compiling.

    The raw text is checked first (:func:`check_source_text`), so nothing
    can make the preprocessor read another file. The source is then
    preprocessed, so comments cannot hide or fake a construct. Checks: no
    ``float``/``double`` or floating literals, no ``*``, ``/`` or ``%``
    operators, and no inline assembly.

    Raises:
        ProgramRejectedError: with the file, line and reason of the first problem.
    """
    check_source_text(c_file.read_text(), c_file.name)
    proc = run_tool([GCC, *COMPILE_FLAGS, "-E", str(c_file)], check=False)
    if proc.returncode != 0:
        raise ProgramRejectedError(_describe_compile_errors(proc.stderr, c_file))

    name = c_file.name
    current_file, line_no = name, 0
    for raw in proc.stdout.splitlines():
        marker = _LINEMARKER.match(raw)
        if marker:
            line_no = int(marker.group(1)) - 1
            current_file = Path(marker.group(2)).name
            continue
        line_no += 1
        if current_file != name:
            continue
        code = _STRING_OR_CHAR.sub('""', raw)
        if m := _INLINE_ASM.search(code):  # already refused above; kept as a second line
            raise ProgramRejectedError(
                f"{name}:{line_no}: inline assembly ('{m.group(1)}') is not supported"
            )
        if m := _FLOAT_KEYWORD.search(code):
            raise ProgramRejectedError(
                f"{name}:{line_no}: '{m.group(1)}' is not supported: "
                "the core has no floating-point unit (F/D extensions)"
            )
        if m := _FLOAT_LITERAL.search(code):
            raise ProgramRejectedError(
                f"{name}:{line_no}: floating-point literal '{m.group(0)}' is not supported: "
                "the core has no floating-point unit (F/D extensions)"
            )
        for op, reason in _OPERATORS.items():
            if op in code:
                raise ProgramRejectedError(f"{name}:{line_no}: {reason}")


# --- compile and link ----------------------------------------------------------


def compile_program(c_file: Path, work_dir: Path) -> CompiledProgram:
    """Check, compile and link ``c_file`` with crt0.S into ``work_dir``.

    Raises:
        ProgramRejectedError: outside the subset, a compile error, a call into
            libc or another undefined function, or an image larger than RAM.
    """
    check_subset(c_file)
    work_dir.mkdir(parents=True, exist_ok=True)
    elf = work_dir / f"{c_file.stem}.elf"
    proc = run_tool(
        [
            GCC,
            *COMPILE_FLAGS,
            f"-ffile-prefix-map={c_file.parent}=.",
            f"-ffile-prefix-map={CRT0.parent}=.",
            "-T",
            str(LINKER_SCRIPT),
            "-o",
            str(elf),
            str(CRT0),
            str(c_file),
        ],
        check=False,
    )
    if proc.returncode != 0:
        raise ProgramRejectedError(_describe_link_errors(proc.stderr, c_file))

    symbols = read_symbols(elf)
    for required in ("_start", "tohost"):
        if required not in symbols:
            raise ToolError(f"linked program has no '{required}' symbol")
    return CompiledProgram(
        elf=elf,
        source_name=c_file.name,
        entry=symbols["_start"],
        tohost=symbols["tohost"],
    )


def _describe_link_errors(stderr: str, c_file: Path) -> str:
    undefined = sorted(set(re.findall(r"undefined reference to [`'](\w+)'", stderr)))
    if undefined:
        reasons: list[str] = []
        libc: list[str] = []
        for sym in undefined:
            if sym in _HELPER_REASONS:
                reasons.append(_HELPER_REASONS[sym])
            elif _FLOAT_HELPER.match(sym):
                reasons.append(f"floating point needs a library routine ({sym}); not supported")
            else:
                libc.append(sym)
        if libc:
            reasons.append(
                "calls into libc or other undefined functions are not supported "
                f"(no C library is linked): {', '.join(libc)}"
            )
        return "; ".join(dict.fromkeys(reasons))
    if "overflowed" in stderr or "exceeds" in stderr:
        return (
            f"the program image does not fit in RAM ({RAM_SIZE} bytes, "
            "including a 512-byte stack); use smaller arrays"
        )
    return _describe_compile_errors(stderr, c_file)


def _describe_compile_errors(stderr: str, c_file: Path) -> str:
    if m := re.search(r"fatal error: (\S+): No such file or directory", stderr):
        return (
            f"header {m.group(1)} is not available: programs run without a C library, "
            "so no #include is supported"
        )
    errors = [
        line.replace(str(c_file.parent) + "/", "")
        for line in stderr.splitlines()
        if ": error:" in line or "fatal error" in line
    ]
    detail = "\n".join(errors[:5]) if errors else stderr.strip()[-2000:]
    return f"compile error:\n{detail}"


def read_symbols(elf: Path) -> dict[str, int]:
    """Return the ELF's symbol table as ``name -> address``."""
    out = run_tool([NM, str(elf)]).stdout
    symbols: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    return symbols


# --- listing and image ---------------------------------------------------------

_INSN = re.compile(r"^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\S+)(?:\s+(.*?))?\s*$")
_SYMBOL = re.compile(r"^([0-9a-f]+) <(.+)>:$")
_LINE_INFO = re.compile(r"^(\S+):(\d+)(?: \(discriminator \d+\))?$")


def normalize_asm(mnemonic: str, operands: str | None) -> str:
    """Join an objdump mnemonic and operands as ``'mnemonic op1,op2'``."""
    ops = (operands or "").strip()
    return f"{mnemonic} {ops}" if ops else mnemonic


def disassemble(program: CompiledProgram) -> list[AsmLine]:
    """Disassemble the program with DWARF line info (``objdump -d -l``).

    ``-M no-aliases`` shows the real instructions the hardware executes
    (``addi a0,zero,0`` rather than ``li a0,0``).
    """
    out = run_tool([OBJDUMP, "-d", "-l", "-M", "no-aliases", str(program.elf)]).stdout
    lines: list[AsmLine] = []
    function = ""
    c_line: int | None = None
    for raw in out.splitlines():
        if m := _SYMBOL.match(raw):
            function = m.group(2)
            c_line = None
            continue
        if m := _LINE_INFO.match(raw.strip()):
            c_line = int(m.group(2)) if Path(m.group(1)).name == program.source_name else None
            continue
        if m := _INSN.match(raw):
            addr = int(m.group(1), 16)
            word = int(m.group(2), 16)
            dec = decode(word)
            lines.append(
                AsmLine(
                    addr=f"0x{addr:08x}",
                    hex=f"0x{word:08x}",
                    text=normalize_asm(m.group(3), m.group(4)),
                    function=function,
                    c_line=c_line,
                    format=dec.format,
                    opcode_name=dec.opcode_name,
                    fields=[
                        InstructionField(
                            name=f.name, hi=f.hi, lo=f.lo, bits=f.bits, meaning=f.meaning
                        )
                        for f in dec.fields
                    ],
                    immediate=dec.immediate,
                )
            )
    if not lines:
        raise ToolError("objdump produced no instructions")
    return lines


def memory_image(program: CompiledProgram, work_dir: Path) -> list[int]:
    """Return the whole RAM as 32-bit little-endian words (zero-filled)."""
    binary = work_dir / f"{program.elf.stem}.bin"
    run_tool(
        [
            OBJCOPY,
            "-O",
            "binary",
            "--gap-fill",
            "0",
            "--pad-to",
            f"0x{RAM_BASE + RAM_SIZE:x}",
            str(program.elf),
            str(binary),
        ]
    )
    data = binary.read_bytes()
    if len(data) != RAM_SIZE:
        raise ProgramRejectedError(
            f"the program image is {len(data)} bytes but RAM is {RAM_SIZE} bytes"
        )
    return [int.from_bytes(data[i : i + 4], "little") for i in range(0, RAM_SIZE, 4)]


def format_hex_image(words: list[int]) -> str:
    """Format words for ``$readmemh``: one ``%08x`` word per line, address order."""
    header = f"// RAM image: {len(words)} words from 0x{RAM_BASE:08x}, little-endian\n"
    return header + "".join(f"{w:08x}\n" for w in words)


# --- round-trip helpers (also used by the tests) -------------------------------

_TARGET = re.compile(r"\b([0-9a-f]{8}) <[^>]*>")
_COMMENT = re.compile(r"\s*#.*$")


_BRANCH_OR_JAL = {"beq", "bne", "blt", "bge", "bltu", "bgeu", "jal"}


def strip_symbols(text: str) -> str:
    """Drop objdump's ``<symbol+off>`` annotations and ``#`` comments.

    Branch and ``jal`` targets are printed ``80000030`` with symbols and
    ``0x80000030`` without; both become ``80000030``.
    """
    text = _COMMENT.sub("", re.sub(r" <[^>]*>", "", text)).strip()
    mnemonic, _, operands = text.partition(" ")
    if mnemonic in _BRANCH_OR_JAL:
        head, sep, target = operands.rpartition(",")
        operands = head + sep + target.removeprefix("0x")
    return normalize_asm(mnemonic, operands)


def assemble(texts: list[str], addrs: list[int], work_dir: Path) -> list[int]:
    """Assemble objdump-style lines placed at ``addrs``; return the words.

    Branch and jump targets printed as ``80000010 <main+0x10>`` become labels,
    so the result is position-exact.
    """
    if not texts:
        return []
    if any(b - a != 4 for a, b in itertools.pairwise(addrs)):
        raise ValueError("addresses must be consecutive words")
    work_dir.mkdir(parents=True, exist_ok=True)
    src = [".option norvc", ".option norelax", ".text", ".globl _start", "_start:"]
    for text, addr in zip(texts, addrs, strict=True):
        body = _COMMENT.sub("", _TARGET.sub(lambda m: f"L{m.group(1)}", text))
        src.append(f"L{addr:08x}: {body}")
    asm = work_dir / "roundtrip.s"
    obj = work_dir / "roundtrip.o"
    elf = work_dir / "roundtrip.elf"
    binary = work_dir / "roundtrip.bin"
    asm.write_text("\n".join(src) + "\n")
    run_tool([AS, *MARCH, "-o", str(obj), str(asm)])
    run_tool([LD, "-m", "elf32lriscv", "-Ttext", f"0x{addrs[0]:x}", "-o", str(elf), str(obj)])
    run_tool([OBJCOPY, "-O", "binary", "-j", ".text", str(elf), str(binary)])
    data = binary.read_bytes()
    return [int.from_bytes(data[i : i + 4], "little") for i in range(0, len(data), 4)]


def disassemble_words(words: list[int], base: int, work_dir: Path) -> list[str]:
    """Disassemble raw words at ``base`` with no symbols; return normalized text."""
    work_dir.mkdir(parents=True, exist_ok=True)
    binary = work_dir / "words.bin"
    binary.write_bytes(b"".join(w.to_bytes(4, "little") for w in words))
    out = run_tool(
        [
            OBJDUMP,
            "-D",
            "-b",
            "binary",
            "-m",
            "riscv:rv32",
            "-M",
            "no-aliases",
            f"--adjust-vma=0x{base:x}",
            str(binary),
        ]
    ).stdout
    return [
        normalize_asm(m.group(3), m.group(4)) for raw in out.splitlines() if (m := _INSN.match(raw))
    ]


# --- Spike golden log ----------------------------------------------------------

_COMMIT = re.compile(r"^core\s+\d+:\s+\d+\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$")
_REG_WRITE = re.compile(r"\bx(\d+)\s+0x([0-9a-f]+)")
_MEM = re.compile(r"\bmem\s+0x([0-9a-f]+)")
_MASK = 0xFFFF_FFFF


def run_spike(program: CompiledProgram, max_cycles: int = MAX_CYCLES) -> GoldenArtifact:
    """Run the program on Spike and return its commit log up to the halt.

    The log starts at ``_start`` (Spike's boot ROM is dropped) and ends with
    the store to ``tohost``. The program is rejected if it retires more than
    ``max_cycles`` instructions without halting.

    Raises:
        ProgramRejectedError: the program does not halt within ``max_cycles``.
        ToolError: Spike failed or exited before the program halted.
    """
    argv = [
        SPIKE,
        f"--isa={SPIKE_ISA}",
        f"-m0x{RAM_BASE:x}:0x{RAM_SIZE:x}",
        "--log-commits",
        str(program.elf),
    ]
    entries: list[GoldenEntry] = []
    tail: list[str] = []
    started = halted = False
    with ToolStream(argv, timeout=SPIKE_WALL_TIMEOUT_S) as spike:
        for raw in spike.lines():
            m = _COMMIT.match(raw.strip())
            if not m:
                tail = [*tail[-20:], raw.rstrip()]
                continue
            pc = int(m.group(1), 16) & _MASK
            if not started:
                if pc != program.entry:
                    continue  # Spike's boot ROM
                started = True
            rest = m.group(3)
            reg = _REG_WRITE.search(rest)
            entries.append(
                GoldenEntry(
                    pc=f"0x{pc:08x}",
                    insn=f"0x{int(m.group(2), 16) & _MASK:08x}",
                    rd=int(reg.group(1)) if reg else None,
                    rd_value=f"0x{int(reg.group(2), 16) & _MASK:08x}" if reg else None,
                )
            )
            mem = _MEM.search(rest)
            if mem and (int(mem.group(1), 16) & _MASK) == program.tohost:
                halted = True
                break
            if len(entries) > max_cycles:
                break
        if not halted:
            spike.stop()
            if len(entries) > max_cycles:
                raise ProgramRejectedError(
                    f"the program did not halt within {max_cycles} cycles "
                    "(check for an infinite loop)"
                )
            raise ToolError("spike exited before the program halted: " + " | ".join(tail))
        exit_code = spike.finish(timeout=10)  # let Spike notice tohost and exit

    a0 = next((e.rd_value for e in reversed(entries) if e.rd == 10), None)
    return GoldenArtifact(
        isa=SPIKE_ISA,
        retired=len(entries),
        max_cycles=max_cycles,
        exit_code=exit_code,
        a0_at_halt=a0 or "0x00000000",
        entries=entries,
    )
