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
    b.w Debug_After_Markers
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

/* EXPERIMENT ONLY: secure debug enable after the original two marker edges.
 * ST's documented debug-control writes; no OTP or lifecycle programming. */
.section .text.Debug_After_Markers,"ax",%progbits
.global Debug_After_Markers
.type Debug_After_Markers,%function
.thumb_func
Debug_After_Markers:
    ldr r0, =BT_RCC_BASE
    movs r1, #2
    str r1, [r0, #0xA78]  /* RCC_APB4ENSR2.BSECENS */
    ldr r1, [r0, #0x278]
    dsb sy
    ldr r0, =0x56009000
    ldr r1, =0xB451B400
    str r1, [r0, #0xE8C]  /* BSEC_DBGCR */
    movs r1, #0xB4
    str r1, [r0, #0xE90]  /* BSEC_AP_UNLOCK */
    dsb sy
    isb sy

    ldr r0, =BT_RCC_BASE
    movs r1, #1
    str r1, [r0, #0xA48]  /* RCC_MISCENSR.DBGENS */
    str r1, [r0, #0xA88]  /* RCC_MISCLPENSR.DBGLPENS */
    ldr r1, [r0, #0x248]
    dsb sy
    ldr r0, =0x54001000
    ldr r1, [r0, #4]
    orr r1, r1, #0x00100000  /* DBGMCU_CR.DBGCLKEN */
    orr r1, r1, #1           /* DBGMCU_CR.DBG_SLEEP */
    str r1, [r0, #4]
    dsb sy
    isb sy

    ldr r2, =0x34182000
    ldr r1, [r0, #4]
    str r1, [r2, #16]
    ldr r0, =0x56009000
    ldr r1, [r0, #0xE8C]
    str r1, [r2, #0]
    ldr r1, [r0, #0xE90]
    str r1, [r2, #4]
    ldr r0, =BT_RCC_BASE
    ldr r1, [r0, #0x44C]  /* RCC_RDCR: read only */
    str r1, [r2, #8]
    ldr r1, [r0, #0x248]
    str r1, [r2, #20]
    ldr r1, [r0, #0x288]
    str r1, [r2, #24]
    ldr r1, =0x44424732
    str r1, [r2, #12]
    dsb sy
    ldr r0, =0xE000EF68   /* SCB_DCCMVAC: clean status cache line */
    str r2, [r0]
    dsb sy
    isb sy
.global debug_ready
debug_ready:
    nop                    /* Stay awake so HOTPLUG need not wake the core. */
    b debug_ready
.size Debug_After_Markers, .-Debug_After_Markers
.ltorg
