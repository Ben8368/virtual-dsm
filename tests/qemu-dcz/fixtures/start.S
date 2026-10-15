.section .text.boot
.global _start, secondary_start
_start:
    ldr x0, =stack_top
    mov sp, x0
    ldr x0, =vectors
    msr vbar_el1, x0
    isb
    bl main
    b .
secondary_start:
    ldr x0, =secondary_stack_top
    mov sp, x0
    ldr x0, =vectors
    msr vbar_el1, x0
    isb
    bl secondary_main
    b .
.balign 2048
vectors:
.rept 16
    b exception
    .balign 128
.endr
exception:
    stp x0, x1, [sp, #-32]!
    stp x2, x30, [sp, #16]
    mrs x0, esr_el1
    mrs x1, elr_el1
    bl handle_exception
    msr elr_el1, x0
    ldp x2, x30, [sp, #16]
    ldp x0, x1, [sp], #32
    eret
.global invoke_expect_fault
invoke_expect_fault:
    stp x29, x30, [sp, #-16]!
    mov x29, sp
    adrp x1, fault_resume
    add x1, x1, :lo12:fault_resume
    adrp x2, expected_resume
    add x2, x2, :lo12:expected_resume
    str x1, [x2]
    blr x0
fault_resume:
    ldp x29, x30, [sp], #16
    ret

.global readonly_zva, unmapped_zva
readonly_zva:
    mov x0, #0x80000000
    dc zva, x0
    ret
unmapped_zva:
    mov x0, #0xc0000000
    dc zva, x0
    ret
