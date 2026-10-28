/* Smaller diagnostic marker payload; does not modify the measured baseline.
 * Assumes PD0/PE0 retain their hardware reset OTYPER/OSPEEDR/PUPDR values:
 * push-pull, low speed, no pull. It explicitly changes only their mode/ODR.
 * Keeps stack limit, stack, complete core vectors and ordinary Sleep setup.
 * No clock-frequency changes, HAL, RTOS, OTP or external-memory writes.
 */
#include "registers.h"
.syntax unified
.arch armv8.1-m.main
.thumb

.section .isr_vector,"a",%progbits
.global g_pfnVectors
.type g_pfnVectors,%object
g_pfnVectors:
    .word _estack
    .word Reset_Handler
    .rept 14
    .word Fault_Handler
    .endr
.size g_pfnVectors, .-g_pfnVectors

.section .text.Reset_Handler,"ax",%progbits
.global Reset_Handler
.type Reset_Handler,%function
.thumb_func
Reset_Handler:
    cpsid i
    ldr r0, =_sstack
    msr MSPLIM, r0
    ldr r0, =_estack
    mov sp, r0
    ldr r0, =BT_SCB_VTOR
    ldr r1, =g_pfnVectors
    str r1, [r0]
    dsb sy
    isb sy

    ldr r0, =BT_RCC_BASE
    movs r1, #BT_GPIOD_GPIOE_ENABLE
    str r1, [r0, #BT_RCC_AHB4ENSR]
    ldr r1, [r0, #BT_RCC_AHB4ENR]
    dsb sy

    movs r2, #1
    ldr r0, =BT_GPIOD_BASE
    str r2, [r0, #BT_GPIO_BSRR]
    ldr r1, [r0, #BT_GPIO_MODER]
    bfi r1, r2, #0, #2
.global pd0_first_edge_store
pd0_first_edge_store:
    str r1, [r0, #BT_GPIO_MODER]
    dsb sy

    ldr r0, =BT_GPIOE_BASE
    str r2, [r0, #BT_GPIO_BSRR]
    ldr r1, [r0, #BT_GPIO_MODER]
    bfi r1, r2, #0, #2
.global pe0_second_edge_store
pe0_second_edge_store:
    str r1, [r0, #BT_GPIO_MODER]
    dsb sy

    ldr r0, =BT_SCB_SCR
    ldr r1, [r0]
    bic r1, r1, #BT_SCB_SLEEPDEEP
    str r1, [r0]
    dsb sy
.global boot_markers_ready
.global boot_idle
boot_markers_ready:
boot_idle:
    wfi
    b boot_idle
.size Reset_Handler, .-Reset_Handler
.ltorg

.section .text.Fault_Handler,"ax",%progbits
.global Fault_Handler
.type Fault_Handler,%function
.thumb_func
Fault_Handler:
    b Fault_Handler
.size Fault_Handler, .-Fault_Handler
.section .note.GNU-stack,"",%progbits
