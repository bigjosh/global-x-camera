.syntax unified
.thumb
.section .text.entry,"ax",%progbits
.global ROM_NOR_Programmer
.type ROM_NOR_Programmer,%function
.thumb_func
ROM_NOR_Programmer:
    cpsid i
    mrs r0, MSP
    mrs r1, MSPLIM
    movs r2, #0
    msr MSPLIM, r2
    ldr r2, =0x341B8000
    msr MSP, r2
    b.w rom_nor_programmer
.size ROM_NOR_Programmer, .-ROM_NOR_Programmer
.ltorg
