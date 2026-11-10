/* GPIO HOLD executes before the original stack/VTOR startup.
 * Only r0/r1 are scratch; no SRAM, stack, FPU, IRQ or peripheral reset used.
 * Addresses/masks correspond to stm32n657xx.h secure RCC/GPIOD aliases. */
.syntax unified
.thumb
.section .gpio_hold_boot,"ax",%progbits
.global gpio_hold_boot
.type gpio_hold_boot,%function
.thumb_func
gpio_hold_boot:
    cpsid i
    ldr r0, =0x56028A5C /* RCC AHB4ENSR: atomic GPIOD clock enable */
    movs r1, #8
    str r1, [r0]
    ldr r0, =0x5602825C /* RCC AHB4ENR readback before GPIO access */
    ldr r1, [r0]
    ldr r0, =0x56020C00 /* GPIOD */
    movs r1, #128
    str r1, [r0, #24] /* BSRR: preload PD7 HIGH before changing mode */
    ldr r1, [r0, #4]
    bic.w r1, r1, #128
    str r1, [r0, #4] /* PD7 push-pull */
    ldr r1, [r0, #8]
    bic.w r1, r1, #0xC000
    str r1, [r0, #8] /* PD7 low speed */
    ldr r1, [r0, #12]
    bic.w r1, r1, #0xC000
    str r1, [r0, #12] /* PD7 no pulls */
    ldr r1, [r0]
    bic.w r1, r1, #0xC000
    orr.w r1, r1, #0x4000
    str r1, [r0] /* PD7 output; other pins preserved */
    dsb
    b.w Stage1_Reset_Handler
.size gpio_hold_boot, .-gpio_hold_boot
.ltorg
