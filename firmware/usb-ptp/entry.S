.syntax unified
.thumb
.section .vectors,"a",%progbits
.global usb_vectors
usb_vectors:
 .word 0x343F0000
 .word usb_entry
 .rept 191
 .word usb_fault
 .endr
 .word USB1_OTG_HS_IRQHandler
 .rept 30
 .word usb_fault
 .endr
.section .text.entry,"ax",%progbits
.global usb_entry
.type usb_entry,%function
.thumb_func
usb_entry:
 cpsid i
 movs r0,#0
 msr MSPLIM,r0
 ldr r0,=0x343F0000
 msr MSP,r0
 ldr r0,=0x343EC000
 msr MSPLIM,r0
 ldr r0,=0xE000ED08
 ldr r1,=usb_vectors
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
 b.w usb_main
.global usb_park
.type usb_park,%function
.thumb_func
usb_park:
 b.n usb_park
.ltorg
