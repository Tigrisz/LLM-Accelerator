.section .text.start
.globl _start
.option norvc
_start:
    li a2, 0xff98
    li a4, 0xff80
    j sequence
    .balign 8
sequence:
    addi a2, a2, -1
    sub a2, a2, a4
    andi a2, a2, -4
    xori a0, a2, 20
    lui t0, 0x10000
    sw a0, 4(t0)
1:  j 1b
