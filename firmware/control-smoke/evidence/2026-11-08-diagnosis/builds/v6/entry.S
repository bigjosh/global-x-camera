.syntax unified
.thumb
.section .vectors,"a",%progbits
.global control_vectors
control_vectors:
 .word 0x343B0000
 .word control_entry
 .rept 222
 .word control_fault
 .endr
.section .text.entry,"ax",%progbits
.global control_entry
.type control_entry,%function
.thumb_func
control_entry:
 cpsid i
 movs r0,#0
 msr MSPLIM,r0
 ldr r0,=0x343B0000
 msr MSP,r0
 ldr r0,=0x343AF000
 msr MSPLIM,r0
 ldr r0,=0xE000ED08
 ldr r1,=control_vectors
 str r1,[r0]
 dsb
 isb
 ldr r0,=__bss_start__
 ldr r1,=__bss_end__
 movs r2,#0
1:
 cmp r0,r1
 bhs 2f
 str r2,[r0],#4
 b 1b
2:
 b.w control_main
.global control_park
.type control_park,%function
.thumb_func
control_park:
 b.n control_park
.ltorg
