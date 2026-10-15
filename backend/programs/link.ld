/* One 4 KiB RAM at 0x80000000 holds code, data and the stack.
 * Must match RAM_BASE / RAM_SIZE in src/app/software.py and backend/rtl/ram.sv. */
OUTPUT_ARCH("riscv")
ENTRY(_start)

MEMORY
{
    RAM (rwx) : ORIGIN = 0x80000000, LENGTH = 4K
}

STACK_SIZE = 512;

SECTIONS
{
    .text   : { *(.text.init) *(.text .text.*) } > RAM
    .rodata : { *(.rodata .rodata.* .srodata .srodata.*) } > RAM
    .data   : { *(.data .data.* .sdata .sdata.*) } > RAM
    .bss    : { *(.bss .bss.* .sbss .sbss.* COMMON) } > RAM
    .tohost : { *(.tohost) } > RAM

    . = ALIGN(16);
    _end = .;
    __stack_top = ORIGIN(RAM) + LENGTH(RAM);
    ASSERT(_end + STACK_SIZE <= __stack_top,
           "program image exceeds RAM: image plus the 512-byte stack must fit in 4 KiB")
}
