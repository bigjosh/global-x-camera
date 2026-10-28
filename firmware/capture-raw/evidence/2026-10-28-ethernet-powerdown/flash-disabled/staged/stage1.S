.syntax unified
.thumb
.section .isr_vector,"a",%progbits
.global stage1_vectors
stage1_vectors:
    .word 0x34188000
    .word Stage1_Reset_Handler
    .rept 14
    .word stage1_fault
    .endr

.section .text.entry,"ax",%progbits
.global Stage1_Reset_Handler
.type Stage1_Reset_Handler,%function
.thumb_func
Stage1_Reset_Handler:
    cpsid i
    movs r0, #0
    msr MSPLIM, r0
    ldr r0, =0x34188000
    msr MSP, r0
    ldr r0, =0xE000ED08
    ldr r1, =stage1_vectors
    str r1, [r0]
    dsb
    isb
    b.w stage1_main
.size Stage1_Reset_Handler, .-Stage1_Reset_Handler
.ltorg

.section .text.stage1_jump,"ax",%progbits
.global stage1_jump
.type stage1_jump,%function
.thumb_func
stage1_jump:
    ldr r1, [r0]
    ldr r2, [r0, #4]
    ldr r3, =0xE000ED08
    str r0, [r3]
    dsb
    isb
    movs r3, #0
    msr MSPLIM, r3
    msr MSP, r1
    bx r2
.size stage1_jump, .-stage1_jump
.ltorg
