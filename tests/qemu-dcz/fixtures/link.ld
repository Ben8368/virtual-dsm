ENTRY(_start)
SECTIONS {
    . = 0x40080000;
    .text : { KEEP(*(.text.boot)) *(.text*) }
    .rodata : { *(.rodata*) }
    .data : { *(.data*) }
    . = ALIGN(4096);
    .bss : { __bss_start = .; *(.bss*) *(COMMON) __bss_end = .; }
    . = ALIGN(16);
    . += 0x10000;
    stack_top = .;
    . += 0x10000;
    secondary_stack_top = .;
}
