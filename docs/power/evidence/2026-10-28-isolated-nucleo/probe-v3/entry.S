.syntax unified
.thumb
.section .vectors,"a",%progbits
.global isolated_vectors
isolated_vectors:
 .word 0x343B0000
 .word isolated_entry
 .rept 13
 .word isolated_fault
 .endr
 .word SysTick_Handler
 .rept 208
 .word isolated_fault
 .endr
.section .text.entry,"ax",%progbits
.global isolated_entry
.type isolated_entry,%function
.thumb_func
isolated_entry:
 cpsid i
 movs r0,#0
 msr MSPLIM,r0
 ldr r0,=0x343B0000
 msr MSP,r0
 ldr r0,=0x343AF000
 msr MSPLIM,r0
 ldr r0,=0xE000ED08
 ldr r2,[r0]
 ldr r1,=isolated_vectors
 str r1,[r0]
 dsb
 isb
 mov r0,r2
 b.w isolated_main
.global isolated_park
.type isolated_park,%function
.thumb_func
isolated_park:
 b.n isolated_park
.ltorg
