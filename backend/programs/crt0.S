# Minimal start-up code: set the stack, call main, then halt.
#
# Halting: store (exit_code << 1) | 1 to `tohost`. Spike's HTIF sees the
# store and exits with exit_code; the hardware simulation stops on the same
# store. a0 is left holding main's return value.

    .section .text.init, "ax", @progbits
    .globl _start
_start:
    la    sp, __stack_top
    # Spike's boot ROM leaves t0, a0 and a1 non-zero; clear them so the
    # register file starts at all zeros, as it does on the hardware.
    addi  t0, zero, 0
    addi  a0, zero, 0
    addi  a1, zero, 0
    call  main
    slli  t1, a0, 1
    ori   t1, t1, 1
    la    t0, tohost
    sw    t1, 0(t0)
1:  j     1b

    .section .tohost, "aw", @progbits
    .balign 8
    .globl tohost
tohost:
    .word 0, 0
    .globl fromhost
fromhost:
    .word 0, 0
