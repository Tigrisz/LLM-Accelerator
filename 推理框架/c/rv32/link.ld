OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0, LENGTH = 64K }
PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }
SECTIONS {
    .text : { KEEP(*(.text.start)) *(.text .text.*) } > RAM :text
    .rodata : { *(.rodata .rodata.*) } > RAM :text
    .data : { *(.data .data.*) . = ALIGN(8); } > RAM :data
    .sdata : { __global_pointer$ = . + 0x800; *(.sdata .sdata.*) } > RAM :data
    .bss (NOLOAD) : {
        . = ALIGN(8); __bss_start = .;
        *(.sbss .sbss.* .bss .bss.* COMMON)
        . = ALIGN(8); __bss_end = .;
    } > RAM :data
    __image_data_end = .;
    .stack 0xE000 (NOLOAD) : { __stack_bottom = .; . += 8192; __stack_top = .; } > RAM :data
    ASSERT(__image_data_end <= __stack_bottom, "TCM image/static buffers overlap reserved stack")
    ASSERT(__stack_top == 0x10000, "Unexpected stack top")
    /DISCARD/ : { *(.eh_frame*) }
}
