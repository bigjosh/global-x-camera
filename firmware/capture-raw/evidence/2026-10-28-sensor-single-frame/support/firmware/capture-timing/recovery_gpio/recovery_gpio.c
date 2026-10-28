/* Early, volatile debug recovery for the bench prefix. No sensor, DMA, XSPI,
 * memory-bank-power, OTP, reset, or ROM-entry operation belongs in this file.
 * Only SRAM already available to the ROM prefix is used before check returns.
 */
#include <stdint.h>
#include "stm32n657xx.h"
#include "recovery_gpio.h"

#define GUARD ((volatile uint32_t *)0x341F7000U)
#define PUBLISHED ((volatile uint32_t *)0x343F7000U)
#define PIN (1U << 1U) /* PE1, Nucleo CN15.24, main 3.3 V domain. */
#define MODE_MASK (3U << 2U)
#define PULL_UP (1U << 2U)
#define SETTLE_CYCLES 40000U /* 100 nominal us at the existing 400 MHz ROM clock. */
#define MAX_POLLS 100000U /* Timer failure must still reach an awake debug park. */
#define MAGIC 0x52475031U /* RGP1 */

enum {
    G_MAGIC, G_SCHEMA, G_WORDS, G_STATE, G_REASON, G_PIN,
    G_NOMINAL_HZ, G_SETTLE_CYCLES, G_BEGIN_CYCLE, G_SAMPLE_CYCLE,
    G_ELAPSED_CYCLES, G_POLLS, G_IDR, G_MODER, G_PUPDR, G_AHB4ENR,
    G_DEMCR, G_DWT_CTRL, G_CONTROL, G_IPSR, G_PRIMASK, G_DBGCR,
    G_AP_UNLOCK, G_RESERVED, GUARD_WORDS
};
enum { BEGUN=1U, NORMAL=2U, PARKED=3U };
enum { NO_REQUEST=0U, REQUESTED=1U, TIMER_FAILED=2U, BAD_CONTEXT=3U };

/* An exact, externally identifiable CPU state, not sleep or a debugger trap.
 * The controller must verify this instruction and the rest of the exact
 * loaded prefix before considering any maintenance operation. */
__attribute__((naked,noreturn,noinline,used)) void recovery_gpio_park(void)
{
    __asm volatile("1: b 1b");
}

void recovery_gpio_begin(void)
{
    __disable_irq(); /* The vector entry already masks IRQs; retain that policy. */
    for (uint32_t i=0U; i<GUARD_WORDS; ++i) GUARD[i]=0U;
    GUARD[G_SCHEMA]=1U;
    GUARD[G_WORDS]=GUARD_WORDS;
    GUARD[G_STATE]=BEGUN;
    GUARD[G_PIN]=0x00040001U; /* Port index E=4, pin=1. */
    GUARD[G_NOMINAL_HZ]=400000000U;
    GUARD[G_SETTLE_CYCLES]=SETTLE_CYCLES;

    RCC->AHB4ENSR=RCC_AHB4ENSR_GPIOEENS;
    (void)RCC->AHB4ENR;
    GPIOE->MODER &= ~MODE_MASK; /* Input before selecting the weak pull. */
    GPIOE->PUPDR=(GPIOE->PUPDR & ~MODE_MASK) | PULL_UP;
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT=0U;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    __DSB();
    GUARD[G_BEGIN_CYCLE]=DWT->CYCCNT;
    GUARD[G_MAGIC]=MAGIC;
    __DSB();
}

void recovery_gpio_check(void)
{
    uint32_t start=GUARD[G_BEGIN_CYCLE], now=DWT->CYCCNT, polls=0U;
    uint32_t reason=NO_REQUEST;
    if (DWT->CTRL & DWT_CTRL_NOCYCCNT_Msk) reason=TIMER_FAILED;
    while (reason==NO_REQUEST && (uint32_t)(now-start)<SETTLE_CYCLES) {
        if (++polls>=MAX_POLLS) { reason=TIMER_FAILED; break; }
        now=DWT->CYCCNT;
    }
    __DSB();
    uint32_t idr=GPIOE->IDR; /* First actual pin sample follows settling. */
    __disable_irq();
    GUARD[G_SAMPLE_CYCLE]=now;
    GUARD[G_ELAPSED_CYCLES]=(uint32_t)(now-start);
    GUARD[G_POLLS]=polls;
    GUARD[G_IDR]=idr;
    GUARD[G_MODER]=GPIOE->MODER;
    GUARD[G_PUPDR]=GPIOE->PUPDR;
    GUARD[G_AHB4ENR]=RCC->AHB4ENR;
    GUARD[G_DEMCR]=CoreDebug->DEMCR;
    GUARD[G_DWT_CTRL]=DWT->CTRL;
    GUARD[G_CONTROL]=__get_CONTROL();
    GUARD[G_IPSR]=__get_IPSR();
    GUARD[G_PRIMASK]=__get_PRIMASK();
    GUARD[G_DBGCR]=BSEC->DBGCR;
    GUARD[G_AP_UNLOCK]=BSEC->AP_UNLOCK;
    if (GUARD[G_CONTROL] || GUARD[G_IPSR] || GUARD[G_PRIMASK]!=1U)
        reason=BAD_CONTEXT;
    if (reason==NO_REQUEST && !(idr & PIN)) reason=REQUESTED;
    GUARD[G_REASON]=reason;
    GUARD[G_STATE]=reason==NO_REQUEST ? NORMAL : PARKED;
    __DSB();
    if (reason!=NO_REQUEST) {
        /* ROM leaves I-cache enabled. Recovery maintenance loads RAM code, so
         * disable/invalidate instruction cache using the CMSIS barrier sequence.
         * Leave D-cache unchanged: an unexpected enabled D-cache must still be
         * rejected by the host's exact-context guard. Normal boot skips this. */
        SCB_DisableICache();
        recovery_gpio_park();
    }
}

void recovery_gpio_publish(void)
{
    /* Called only AFTER raw10_memory_init. The image subsequently overwrites
     * the low address, so successful normal boots preserve the sample here. */
    PUBLISHED[G_MAGIC]=0U;
    for (uint32_t i=1U; i<GUARD_WORDS; ++i) PUBLISHED[i]=GUARD[i];
    __DSB();
    PUBLISHED[G_MAGIC]=GUARD[G_MAGIC];
    __DSB();
}
