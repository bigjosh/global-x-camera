/* Minimal secure FSBL payload for an externally measured first GPIO edge.
 * The Boot ROM has already established clocks, SRAM and secure privilege.
 * No HAL, SystemInit, C runtime, external memory writes or OTP operations.
 */
#include "registers.h"

.syntax unified
.arch armv8.1-m.main
.thumb

/* Only core vectors are needed: maskable interrupts are never enabled.
 * Linker places this table at the STM32N6-required 0x400 alignment.
 */
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

    /* Set a fault-safe stack and vector base before peripheral accesses. */
    ldr r0, =_sstack
    msr MSPLIM, r0
    ldr r0, =_estack
    mov sp, r0
    ldr r0, =BT_SCB_VTOR
    ldr r1, =g_pfnVectors
    str r1, [r0]
    dsb sy
    isb sy

    /* Same enable/readback sequence as ST's LL_AHB4_GRP1_EnableClock(). */
    ldr r0, =BT_RCC_BASE
    movs r1, #BT_GPIOD_GPIOE_ENABLE
    str r1, [r0, #BT_RCC_AHB4ENSR]
    ldr r1, [r0, #BT_RCC_AHB4ENR]
    dsb sy

    /* Touch only PD0. Preload high; changing MODER creates the first edge.
     * Explicit pin-only settings avoid relying on ROM-retained port values.
     * Low slew rate is adequate for a single latched measurement marker.
     */
    ldr r0, =BT_GPIOD_BASE
    ldr r1, [r0, #BT_GPIO_OTYPER]
    bic r1, r1, #1
    str r1, [r0, #BT_GPIO_OTYPER]
    ldr r1, [r0, #BT_GPIO_OSPEEDR]
    bic r1, r1, #3
    str r1, [r0, #BT_GPIO_OSPEEDR]
    ldr r1, [r0, #BT_GPIO_PUPDR]
    bic r1, r1, #3
    str r1, [r0, #BT_GPIO_PUPDR]
    movs r1, #1
    str r1, [r0, #BT_GPIO_BSRR]
    ldr r1, [r0, #BT_GPIO_MODER]
    bic r1, r1, #3
    orr r1, r1, #1
.global pd0_first_edge_store
pd0_first_edge_store:
    str r1, [r0, #BT_GPIO_MODER]
    dsb sy

    /* PE0 confirms that execution continued beyond the first marker. */
    ldr r0, =BT_GPIOE_BASE
    ldr r1, [r0, #BT_GPIO_OTYPER]
    bic r1, r1, #1
    str r1, [r0, #BT_GPIO_OTYPER]
    ldr r1, [r0, #BT_GPIO_OSPEEDR]
    bic r1, r1, #3
    str r1, [r0, #BT_GPIO_OSPEEDR]
    ldr r1, [r0, #BT_GPIO_PUPDR]
    bic r1, r1, #3
    str r1, [r0, #BT_GPIO_PUPDR]
    movs r1, #1
    str r1, [r0, #BT_GPIO_BSRR]
    ldr r1, [r0, #BT_GPIO_MODER]
    bic r1, r1, #3
    orr r1, r1, #1
.global pe0_second_edge_store
pe0_second_edge_store:
    str r1, [r0, #BT_GPIO_MODER]
    dsb sy

    /* Ordinary Sleep only; hold the two marker outputs high until reset.
     * This experiment does not qualify minimum idle current or energy.
     */
    ldr r0, =BT_SCB_SCR
    ldr r1, [r0]
    bic r1, r1, #BT_SCB_SLEEPDEEP
    str r1, [r0]
    dsb sy
.global boot_markers_ready
.global boot_idle
boot_markers_ready:
boot_idle:
    b.w Post_Marker_Entry
    nop
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

.section .text.Post_Marker_Entry,"ax",%progbits
.global Post_Marker_Entry
.type Post_Marker_Entry,%function
.thumb_func
Post_Marker_Entry:
    ldr r3, =0x56028000
    ldr r0, [r3, #0x264]
    mov r1, #-1
    mov r2, #-1
#ifndef SKIP_TIM2
    tst r0, #1
    beq 1f
    ldr r3, =0x50000000
    ldr r1, [r3, #0x24]
    ldr r2, [r3, #0x28]
#endif
1:  mrs r3, CONTROL
    b.w fallback_dump
.size Post_Marker_Entry, .-Post_Marker_Entry
.ltorg
