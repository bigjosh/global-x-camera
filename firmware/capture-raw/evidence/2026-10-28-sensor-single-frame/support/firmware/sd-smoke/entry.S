.syntax unified
.thumb
.section .text.entry,"ax",%progbits
.global SD_Read_Smoke
.type SD_Read_Smoke,%function
.thumb_func
SD_Read_Smoke:
    cpsid i
    mrs r0, MSP
    mrs r1, MSPLIM
    movs r2, #0
    msr MSPLIM, r2
    ldr r2, =0x341B8000
    msr MSP, r2
    b.w sd_read_smoke
.size SD_Read_Smoke, .-SD_Read_Smoke
.ltorg
