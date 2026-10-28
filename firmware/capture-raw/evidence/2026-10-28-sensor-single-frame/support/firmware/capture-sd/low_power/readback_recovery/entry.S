.syntax unified
.thumb
.section .entry,"ax",%progbits
.global readback_boot_entry
.thumb_func
readback_boot_entry:
    cpsid i
    movs r0,#0
    msr msplim,r0
    ldr sp,=0x341B8000
    ldr r0,=0x341B6000
    msr msplim,r0
    bl readback_boot_main
.global readback_boot_park
readback_boot_park:
1:  b.n 1b
.ltorg
