"""Each cycle in plain words: what the instruction did, and where to see it.

Written for a reader who has never seen assembly. Every value comes from the
verified gate-level trace (register reads, the ALU's answer, the next PC) or
Spike's log (the value written). "What to look for" names only blocks and
wires that are on the datapath drawing; ``tests/test_explain.py`` checks both.
"""

import re
from dataclasses import dataclass

from app.decode import ABI_NAMES
from app.errors import PipelineError
from app.models import AsmLine, Explanation, ExplanationKind, ProgramArtifact
from app.views.trace import TraceIndex

DP = "rv.dp."  # trace signals of the datapath
ALU_VIEW = "top.rv.dp.alu"

R_TYPE = {"add", "sub", "and", "or", "xor", "sll", "srl", "sra", "slt", "sltu"}
I_TYPE = {"addi", "andi", "ori", "xori", "slli", "srli", "srai", "slti", "sltiu"}
LOADS = {"lb": "byte", "lh": "halfword (2 bytes)", "lw": "word (4 bytes)",
         "lbu": "byte", "lhu": "halfword (2 bytes)"}  # fmt: skip
STORES = {"sb": "lowest byte", "sh": "lowest 2 bytes", "sw": "4 bytes"}
CONDITIONS = {
    "beq": ("equal to", False), "bne": ("not equal to", False),
    "blt": ("less than", False), "bge": ("greater than or equal to", False),
    "bltu": ("less than", True), "bgeu": ("greater than or equal to", True),
}  # fmt: skip
_TARGET_NAME = re.compile(r"<([A-Za-z_][\w.]*)(?:\+0x[0-9a-f]+)?>")


@dataclass(frozen=True)
class Look:
    """The 'what to look for' sentence and the blocks and wires it names."""

    text: str
    blocks: list[str]
    wires: list[str]  # short names; DP is added for the model


@dataclass(frozen=True)
class Cycle:
    """What the explainer needs about one cycle, read from the trace and Spike."""

    text: str
    mnemonic: str
    word: int
    pc: int
    rd: int
    rs1: int
    rs2: int
    rd1: int  # value read for rs1
    rd2: int  # value read for rs2
    immext: int
    aluresult: int
    pcnext: int
    pcsrc: int  # control signals, as the trace has them
    alusrc: int
    regwrite: int
    written: int | None  # the value Spike says rd receives
    ram: range


def _signed(value: int) -> int:
    return value - (1 << 32) if value >> 31 & 1 else value


def show(value: int, ram: range) -> str:
    """A value for a reader: addresses in RAM in hex, other values in signed decimal."""
    value &= 0xFFFF_FFFF
    if value in ram:
        return f"0x{value:08x}"
    signed = _signed(value)
    return str(signed) if abs(signed) < 10_000 else f"{signed} (0x{value:08x})"


def _reg(c: Cycle, reg: int, value: int) -> str:
    """'a5 (= 10)', or 'zero' for x0 (which always reads 0)."""
    return "zero" if reg == 0 else f"{ABI_NAMES[reg]} (= {show(value, c.ram)})"


def _saved(c: Cycle) -> str:
    """Where the answer goes: ', and saves the result, 55, in a0.' or that it is dropped."""
    if c.rd == 0 or c.written is None:
        return ", but the result is thrown away: it goes to zero, which always stays 0."
    return f" and saves the result, {show(c.written, c.ram)}, in {ABI_NAMES[c.rd]}."


# --- what happened --------------------------------------------------------------


def _alu_what(c: Cycle, op: str, x: str, y: str, shamt: int, unsigned_note: bool) -> str:
    """The verb phrase for an ALU operation on ``x`` and ``y``.

    For a shift, ``y`` names where the amount comes from when it is a register
    ("a2 (= 1)"); a shift by a constant passes ``y`` as "".
    """
    places = f"{shamt} place{'' if shamt == 1 else 's'}"
    if y and op in ("sll", "srl", "sra"):
        places += f" (the lowest 5 bits of {y})"
    if op == "add":
        return f"adds {x} and {y}"
    if op == "sub":
        return f"subtracts {y} from {x}"
    if op == "and":
        return f"keeps the bits that are 1 in both {x} and {y} (AND)"
    if op == "or":
        return f"sets each bit that is 1 in {x} or in {y} (OR)"
    if op == "xor":
        return f"sets each bit where {x} and {y} differ (XOR)"
    if op == "sll":
        return f"shifts {x} left by {places}, with 0s coming in at the right,"
    if op == "srl":
        return f"shifts {x} right by {places}, filling with 0s,"
    if op == "sra":
        return (
            f"shifts {x} right by {places}, copying the sign bit in so that a "
            "negative number stays negative,"
        )
    how = (
        "as unsigned numbers (a negative number counts as a huge one)"
        if unsigned_note
        else ("as signed numbers")
    )
    answer = "yes" if c.written == 1 else "no"
    return f"asks whether {x} is less than {y}, {how}: {answer}, so the answer is {c.written}"


def _what_alu(c: Cycle) -> str:
    x, y = _reg(c, c.rs1, c.rd1), _reg(c, c.rs2, c.rd2)
    op = c.mnemonic
    phrase = _alu_what(c, op, x, y, c.rd2 & 31, op == "sltu")
    if op in ("slt", "sltu"):
        return f"`{c.text}` {phrase}" + (
            f", saved in {ABI_NAMES[c.rd]}." if c.rd else ", thrown away (rd is zero)."
        )
    return f"`{c.text}` {phrase if c.rd else phrase.rstrip(',')}{_saved(c)}"


def _what_alu_imm(c: Cycle) -> str:
    op = c.mnemonic[:-1] if c.mnemonic != "sltiu" else "sltu"
    imm = _signed(c.immext)
    if c.mnemonic == "addi" and c.rs1 == 0 and c.rd != 0:
        return (
            f"`{c.text}` puts the number {show(c.immext, c.ram)} into {ABI_NAMES[c.rd]} "
            f"(it adds {imm} to zero, which always holds 0)."
        )
    if c.mnemonic == "addi" and imm == 0 and c.rd != 0:
        return (
            f"`{c.text}` copies {_reg(c, c.rs1, c.rd1)} into {ABI_NAMES[c.rd]} "
            "(it adds the constant 0)."
        )
    x = _reg(c, c.rs1, c.rd1)
    y = "" if op in ("sll", "srl", "sra") else f"the constant {imm}"
    phrase = _alu_what(c, op, x, y, c.immext & 31, op == "sltu")
    if op in ("slt", "sltu"):
        return f"`{c.text}` {phrase}" + (
            f", saved in {ABI_NAMES[c.rd]}." if c.rd else ", thrown away (rd is zero)."
        )
    return f"`{c.text}` {phrase if c.rd else phrase.rstrip(',')}{_saved(c)}"


def _what_load(c: Cycle) -> str:
    size = LOADS[c.mnemonic]
    fill = (
        "padded with 0s to 32 bits"
        if c.mnemonic.endswith("u")
        else "with its top bit copied upward to fill 32 bits"
    )
    extend = "" if c.mnemonic == "lw" else f", {fill}"
    value = show(c.written, c.ram) if c.written is not None else "(nothing)"
    return (
        f"`{c.text}` reads a {size} from memory at address {_reg(c, c.rs1, c.rd1)} "
        f"+ {_signed(c.immext)} = {show(c.aluresult, c.ram)}{extend}, and saves it, "
        f"{value}, in {ABI_NAMES[c.rd]}."
    )


def _what_store(c: Cycle) -> str:
    return (
        f"`{c.text}` writes the {STORES[c.mnemonic]} of {_reg(c, c.rs2, c.rd2)} to "
        f"memory at address {_reg(c, c.rs1, c.rd1)} + {_signed(c.immext)} = "
        f"{show(c.aluresult, c.ram)}. No register changes."
    )


def _what_halt(c: Cycle, a0: int) -> str:
    return (
        f"`{c.text}` is the program's last instruction: it stores to tohost, the "
        "address the simulator watches to know the program has finished. The value "
        f"stored carries main's answer: a0 = {show(a0, c.ram)}."
    )


def _what_branch(c: Cycle) -> str:
    cond, unsigned = CONDITIONS[c.mnemonic]
    x, y = _reg(c, c.rs1, c.rd1), _reg(c, c.rs2, c.rd2)
    how = " (as unsigned numbers)" if unsigned else ""
    taken = c.pcnext != c.pc + 4
    if taken:
        where = "back up, so the loop goes round again" if c.pcnext < c.pc else "skipping ahead"
        outcome = (
            f"yes, so the branch is taken: the next instruction is the one at "
            f"{show(c.pcnext, c.ram)}, {where}."
        )
    else:
        outcome = (
            "no, so the branch is not taken: the processor moves on to the next "
            f"instruction, at {show(c.pcnext, c.ram)}."
        )
    return f"`{c.text}` compares {x} with {y}{how}: is the first {cond} the second? {outcome}"


def _function_name(text: str) -> str | None:
    m = _TARGET_NAME.search(text)
    return m.group(1) if m else None


def _what_jal(c: Cycle) -> tuple[ExplanationKind, str]:
    target = show(c.pcnext, c.ram)
    if c.rd != 0:
        name = _function_name(c.text)
        fn = f"the function {name}" if name else "a function"
        return "call", (
            f"`{c.text}` calls {fn}: it jumps to {target} and saves the return "
            f"address, {show(c.pc + 4, c.ram)} (the instruction after this one), in "
            f"{ABI_NAMES[c.rd]}, so the function knows where to come back to."
        )
    where = " (back up: the loop goes round again)" if c.pcnext < c.pc else " (skipping ahead)"
    return "jump", f"`{c.text}` jumps to {target}{where}; no register changes."


def _what_jalr(c: Cycle) -> tuple[ExplanationKind, str]:
    target = show(c.pcnext, c.ram)
    if c.rd == 0 and c.rs1 == 1 and _signed(c.immext) == 0:
        return "return", (
            f"`{c.text}` returns from the function: it jumps back to the address "
            f"saved in ra, {target}."
        )
    base = f"{_reg(c, c.rs1, c.rd1)} + {_signed(c.immext)}"
    if c.rd != 0:
        return "call", (
            f"`{c.text}` calls the function at {base} = {target} and saves the return "
            f"address, {show(c.pc + 4, c.ram)}, in {ABI_NAMES[c.rd]}."
        )
    return "jump", f"`{c.text}` jumps to the address {base} = {target}."


def _what_upper(c: Cycle) -> str:
    value = show(c.written, c.ram) if c.written is not None else "(nothing)"
    upper = (c.word >> 12) & 0xF_FFFF
    if c.mnemonic == "lui":
        return (
            f"`{c.text}` puts {value} into {ABI_NAMES[c.rd]}: lui loads the upper 20 "
            f"bits of a number (here 0x{upper:x}) with 0s below. Programs use it to "
            "build big numbers and addresses."
        )
    return (
        f"`{c.text}` adds {show(upper << 12, c.ram)} (its 20-bit constant 0x{upper:x}, "
        f"moved to the top of the word) to this instruction's own address, "
        f"{show(c.pc, c.ram)}, and saves {value} in {ABI_NAMES[c.rd]}: a way to find "
        "addresses near the code."
    )


# --- what to look for -------------------------------------------------------------


def _write_back(c: Cycle) -> str:
    """The write-back sentence, with regwrite as the trace has it."""
    if c.rd == 0:
        return "Register zero ignores the write."
    return (
        "The answer goes through the result mux (resultmux) back to the register file "
        f"(rf) as result, and regwrite is {c.regwrite}, so it is saved when the clock "
        "ticks at the end of the cycle."
    )


_ADDRESS = (
    "The ALU (alu) adds rd1 and immext, the offset the immediate unit (ext) cut out of "
    "the instruction, to make the address, aluresult"
)


def _look(c: Cycle, kind: ExplanationKind) -> Look:
    """Where to see this cycle's work on the datapath, by block and wire name."""
    writes = c.rd != 0
    if kind == "alu":
        return Look(
            "Follow rd1 and rd2 out of the register file (rf): rd1 through the A input "
            "mux (srcamux), rd2 through the B input mux (srcbmux), into the ALU (alu), "
            "whose answer is aluresult. " + _write_back(c),
            ["rf", "srcamux", "srcbmux", "alu", "resultmux"],
            ["rd1", "rd2", "aluresult", "result", "regwrite"],
        )
    if kind == "alu_imm":
        return Look(
            "rd1 comes out of the register file (rf), but the ALU's other input is the "
            "constant: the immediate unit (ext) cuts it out of the instruction as "
            "immext, and the B input mux (srcbmux) picks it instead of rd2, because "
            f"alusrc is {c.alusrc}. The ALU (alu) computes aluresult. " + _write_back(c),
            ["rf", "ext", "srcbmux", "alu", "resultmux"],
            ["rd1", "immext", "alusrc", "aluresult", "result", "regwrite"],
        )
    if kind == "load":
        return Look(
            f"{_ADDRESS}, which goes out to memory. The memory's word comes back as "
            "readword; the load/store unit (lsu) picks the right bytes out of it as "
            "loaddata, and the result mux (resultmux) passes loaddata, not the ALU's "
            "answer, to the register file (rf) as result.",
            ["alu", "ext", "lsu", "resultmux", "rf"],
            ["rd1", "immext", "aluresult", "readword", "loaddata", "result"],
        )
    if kind in ("store", "halt"):
        return Look(
            f"{_ADDRESS}. rd2, the value to store, goes into the load/store unit (lsu), "
            "which puts its bytes in place as writedata and sets byteen to say which "
            f"of the word's 4 bytes to write. regwrite is {c.regwrite}: no register changes.",
            ["alu", "ext", "lsu"],
            ["rd1", "immext", "aluresult", "rd2", "writedata", "byteen", "regwrite"],
        )
    if kind == "branch":
        return Look(
            "The ALU (alu) subtracts rd2 from rd1 only to set its flags (zero, neg, "
            "ovf, carry); the control unit turns them into the decision, pcsrc. The PC "
            "mux (pcmux) then picks pctarget, computed by the branch adder "
            "(pcaddbranch), or pcplus4, from the +4 adder (pcadd4). Watch pcnext: it "
            f"becomes the PC at the clock edge. Here pcsrc is {c.pcsrc}, so it picks "
            f"{'pctarget' if c.pcsrc == 1 else 'pcplus4'}.",
            ["alu", "pcmux", "pcaddbranch", "pcadd4"],
            ["rd1", "rd2", "zero", "neg", "ovf", "carry", "pcsrc", "pctarget",
             "pcplus4", "pcnext"],
        )  # fmt: skip
    link = (
        " At the same time pcplus4, the return address, goes through the result mux "
        "(resultmux) to the register file (rf) as result."
        if writes
        else ""
    )
    link_blocks = ["resultmux", "rf"] if writes else []
    link_wires = ["pcplus4", "result"] if writes else []
    if c.mnemonic == "jal":
        return Look(
            "The branch adder (pcaddbranch) adds immext, the jump distance cut out of the "
            "instruction by the immediate unit (ext), to pc to get pctarget, and the PC "
            f"mux (pcmux) picks it as pcnext, because pcsrc is {c.pcsrc}." + link,
            ["pcaddbranch", "ext", "pcmux", *link_blocks],
            ["immext", "pc", "pctarget", "pcsrc", "pcnext", *link_wires],
        )
    if c.mnemonic == "jalr":
        return Look(
            "The ALU (alu) adds rd1 and immext, from the immediate unit (ext). That sum, "
            "aluresult, with its lowest bit cleared, is the target, and the PC mux "
            f"(pcmux) picks it as pcnext, because pcsrc is {c.pcsrc}." + link,
            ["alu", "ext", "pcmux", *link_blocks],
            ["rd1", "immext", "aluresult", "pcsrc", "pcnext", *link_wires],
        )
    first = "the constant 0" if c.mnemonic == "lui" else "pc"
    return Look(
        f"The A input mux (srcamux) picks {first} instead of rd1, and the B input mux "
        "(srcbmux) picks immext from the immediate unit (ext), so the ALU (alu) adds "
        f"them: srca + immext = aluresult. {_write_back(c)}",
        ["srcamux", "srcbmux", "ext", "alu", "resultmux", "rf"],
        [
            "srca",
            "immext",
            "aluresult",
            "result",
            "regwrite",
            *(["pc"] if c.mnemonic == "auipc" else []),
        ],
    )


# --- going deeper -------------------------------------------------------------------


def _deeper(c: Cycle, kind: ExplanationKind) -> tuple[str | None, str | None]:
    op = c.mnemonic.rstrip("i") if kind == "alu_imm" and c.mnemonic != "sltiu" else c.mnemonic
    if kind == "branch" or op in ("add", "sub", "addi") or kind in ("load", "store", "upper"):
        return (
            "Open the ALU's adder to watch the carries ripple from bit 0 to bit 31.",
            f"{ALU_VIEW}.add",
        )
    if op in ("sll", "srl", "sra"):
        return (
            "Open the ALU's shifter to see the shift done in stages of 16, 8, 4, 2 and 1.",
            f"{ALU_VIEW}.sh",
        )
    if op in ("and", "or", "xor"):
        return "Open the ALU's logic unit to see one gate per bit.", f"{ALU_VIEW}.lu"
    if op in ("slt", "sltu", "sltiu"):
        return (
            "Open the ALU's result mux to see the comparison bit chosen as the answer.",
            f"{ALU_VIEW}.rm",
        )
    if kind in ("call", "jump", "return"):
        return "Open the PC mux to see its gates choose the next PC.", "top.rv.dp.pcmux"
    return None, None


# --- the C line -----------------------------------------------------------------------


def _context(line: AsmLine, program: ProgramArtifact) -> str:
    if line.c_line is not None:
        code = program.c_lines[line.c_line - 1].text.strip()
        return f"In the C program this is line {line.c_line}: {code}"
    if line.function == "_start":
        return (
            "This is start-up code (crt0.S), which runs before main: it sets up the "
            "stack, calls main, and reports main's answer when it returns."
        )
    return (
        f"The compiler added this instruction to the function {line.function}; it "
        "belongs to no single C line (saving or restoring registers, for example)."
    )


# --- putting it together -------------------------------------------------------------


def explain(
    n: int,
    line: AsmLine,
    program: ProgramArtifact,
    index: TraceIndex,
    written: int | None,
    a0_at_halt: int,
    last: bool,
) -> Explanation:
    """The plain-language explanation of cycle ``n``, which runs ``line``.

    ``written`` is the value Spike says the instruction writes to its rd (None
    if none), ``a0_at_halt`` main's answer, and ``last`` whether this is the
    halt store.
    """
    word = int(line.hex, 16)
    base = int(program.ram_base, 16)
    c = Cycle(
        text=line.text,
        mnemonic=line.text.split()[0],
        word=word,
        pc=int(line.addr, 16),
        rd=(word >> 7) & 31,
        rs1=(word >> 15) & 31,
        rs2=(word >> 20) & 31,
        rd1=index.value(n, DP + "rd1"),
        rd2=index.value(n, DP + "rd2"),
        immext=index.value(n, DP + "immext"),
        aluresult=index.value(n, DP + "aluresult"),
        pcnext=index.value(n, DP + "pcnext"),
        pcsrc=index.value(n, DP + "pcsrc"),
        alusrc=index.value(n, DP + "alusrc"),
        regwrite=index.value(n, DP + "regwrite"),
        written=written,
        ram=range(base, base + program.ram_size_bytes + 1),  # the stack starts at the end
    )
    kind: ExplanationKind
    if last and c.mnemonic in STORES:
        kind, what = "halt", _what_halt(c, a0_at_halt)
    elif c.mnemonic in R_TYPE:
        kind, what = "alu", _what_alu(c)
    elif c.mnemonic in I_TYPE:
        kind, what = "alu_imm", _what_alu_imm(c)
    elif c.mnemonic in LOADS:
        kind, what = "load", _what_load(c)
    elif c.mnemonic in STORES:
        kind, what = "store", _what_store(c)
    elif c.mnemonic in CONDITIONS:
        kind, what = "branch", _what_branch(c)
    elif c.mnemonic == "jal":
        kind, what = _what_jal(c)
    elif c.mnemonic == "jalr":
        kind, what = _what_jalr(c)
    elif c.mnemonic in ("lui", "auipc"):
        kind, what = "upper", _what_upper(c)
    else:
        raise PipelineError(f"cycle {n}: no explanation for '{c.mnemonic}'")
    look = _look(c, kind)
    deeper, deeper_view = _deeper(c, kind)
    return Explanation(
        kind=kind,
        what=what,
        context=_context(line, program),
        look_for=look.text,
        blocks=look.blocks,
        wires=[DP + w for w in look.wires],
        deeper=deeper,
        deeper_view=deeper_view,
    )
