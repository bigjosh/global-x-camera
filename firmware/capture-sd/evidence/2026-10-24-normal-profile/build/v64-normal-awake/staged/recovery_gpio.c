/* Additive PE6 VCP pulse request; PE1 recovery remains supported. No sensor,
 * DMA, XSPI, memory-bank-power, OTP, reset or ROM-entry operation belongs here.
 * This uses only low SRAM already available to the ROM prefix.
 */
#include <stdint.h>
#include "stm32n657xx.h"
#include "recovery_gpio.h"
#include "pulse_detector.h"

#define GUARD ((volatile uint32_t *)0x341F7000U)
#define PUBLISHED ((volatile uint32_t *)0x343F7000U)
#define VCP ((volatile uint32_t *)0x341F7080U)
#define VCP_PUBLISHED ((volatile uint32_t *)0x343F7080U)
#define PIN (1U << 1U)
#define VCP_PIN (1U << 6U)
#define MODE_MASK (3U << 2U)
#define VCP_MODE_MASK (3U << 12U)
#define PULL_UP (1U << 2U)
#define VCP_PULL_UP (1U << 12U)
#define SETTLE_CYCLES 40000U
#define MAX_POLLS 100000U
#define MAGIC 0x52475031U
#define VCP_MAGIC 0x56504331U

enum {
    G_MAGIC, G_SCHEMA, G_WORDS, G_STATE, G_REASON, G_PIN,
    G_NOMINAL_HZ, G_SETTLE_CYCLES, G_BEGIN_CYCLE, G_SAMPLE_CYCLE,
    G_ELAPSED_CYCLES, G_POLLS, G_IDR, G_MODER, G_PUPDR, G_AHB4ENR,
    G_DEMCR, G_DWT_CTRL, G_CONTROL, G_IPSR, G_PRIMASK, G_DBGCR,
    G_AP_UNLOCK, G_RESERVED, GUARD_WORDS
};
enum {
    V_MAGIC, V_SCHEMA, V_WORDS, V_PIN, V_NOMINAL_HZ, V_WINDOW_CYCLES,
    V_BAUD, V_MIN_LOW, V_MAX_LOW, V_MIN_HIGH, V_MAX_HIGH, V_REQUIRED,
    V_FIRST_CYCLE, V_LAST_CYCLE, V_EDGES, V_GOOD_PULSES, V_BAD_PULSES,
    V_MAX_TRAIN, V_LAST_LOW, V_LAST_HIGH, V_REQUEST, V_REQUEST_CYCLE,
    V_INITIAL_LEVEL, V_FINAL_LEVEL, V_SOURCE_BITS, V_POLLS,
    V_RESERVED_26, V_RESERVED_27, V_RESERVED_28, V_RESERVED_29,
    V_RESERVED_30, V_RESERVED_31, VCP_WORDS
};
enum { BEGUN=1U, NORMAL=2U, PARKED=3U };
enum { NO_REQUEST=0U, REQUESTED=1U, TIMER_FAILED=2U, BAD_CONTEXT=3U };

__attribute__((naked,noreturn,noinline,used)) void recovery_gpio_park(void)
{
    __asm volatile("1: b 1b");
}

void recovery_gpio_begin(void)
{
    __disable_irq();
    for (uint32_t i=0U; i<GUARD_WORDS; ++i) GUARD[i]=0U;
    GUARD[G_SCHEMA]=1U;
    GUARD[G_WORDS]=GUARD_WORDS;
    GUARD[G_STATE]=BEGUN;
    GUARD[G_PIN]=0x00040001U;
    GUARD[G_NOMINAL_HZ]=400000000U;
    GUARD[G_SETTLE_CYCLES]=SETTLE_CYCLES;

    RCC->AHB4ENSR=RCC_AHB4ENSR_GPIOEENS;
    (void)RCC->AHB4ENR;
    GPIOE->MODER &= ~(MODE_MASK | VCP_MODE_MASK);
    GPIOE->PUPDR=(GPIOE->PUPDR & ~(MODE_MASK | VCP_MODE_MASK)) |
                 PULL_UP | VCP_PULL_UP;
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT=0U;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    __DSB();
    GUARD[G_BEGIN_CYCLE]=DWT->CYCCNT;
    GUARD[G_MAGIC]=MAGIC;
    /* Diagnostics initialization consumes the existing settle interval rather
     * than adding a fresh delay in front of it. */
    for (uint32_t i=0U; i<VCP_WORDS; ++i) VCP[i]=0U;
    VCP[V_SCHEMA]=1U;
    VCP[V_WORDS]=VCP_WORDS;
    VCP[V_PIN]=0x00040006U;
    VCP[V_NOMINAL_HZ]=400000000U;
    VCP[V_WINDOW_CYCLES]=VCP_WINDOW_CYCLES;
    VCP[V_BAUD]=1000000U;
    VCP[V_MIN_LOW]=VCP_MIN_LOW_CYCLES;
    VCP[V_MAX_LOW]=VCP_MAX_LOW_CYCLES;
    VCP[V_MIN_HIGH]=VCP_MIN_HIGH_CYCLES;
    VCP[V_MAX_HIGH]=VCP_MAX_HIGH_CYCLES;
    VCP[V_REQUIRED]=VCP_REQUIRED_PULSES;
    __DSB();
}

void recovery_gpio_check(void)
{
    uint32_t start=GUARD[G_BEGIN_CYCLE], now=DWT->CYCCNT, polls=0U;
    uint32_t reason=NO_REQUEST;
    recovery_vcp_detector detector;
    uint32_t initial_level=!!(GPIOE->IDR & VCP_PIN);
    recovery_vcp_init(&detector,now,initial_level);
    if (DWT->CTRL & DWT_CTRL_NOCYCCNT_Msk) reason=TIMER_FAILED;
    while (reason==NO_REQUEST && (uint32_t)(now-start)<SETTLE_CYCLES) {
        if (++polls>=MAX_POLLS) { reason=TIMER_FAILED; break; }
        /* Sample only inside the existing settle deadline. Do not extend it
         * waiting for a complete byte, another pulse, or a USB burst gap. */
        uint32_t level=GPIOE->IDR & VCP_PIN;
        now=DWT->CYCCNT;
        if ((uint32_t)(now-start)<SETTLE_CYCLES)
            recovery_vcp_sample(&detector,now,level);
    }
    __DSB();
    uint32_t idr=GPIOE->IDR;
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
    uint32_t sources=(!(idr & PIN) ? 1U : 0U) | (detector.request ? 2U : 0U);
    GUARD[G_RESERVED]=sources;
    if (GUARD[G_CONTROL] || GUARD[G_IPSR] || GUARD[G_PRIMASK]!=1U)
        reason=BAD_CONTEXT;
    if (reason==NO_REQUEST && sources) reason=REQUESTED;
    GUARD[G_REASON]=reason;
    GUARD[G_STATE]=reason==NO_REQUEST ? NORMAL : PARKED;
    VCP[V_FIRST_CYCLE]=detector.first_cycle;
    VCP[V_LAST_CYCLE]=now;
    VCP[V_EDGES]=detector.edges;
    VCP[V_GOOD_PULSES]=detector.good_pulses;
    VCP[V_BAD_PULSES]=detector.bad_pulses;
    VCP[V_MAX_TRAIN]=detector.max_train;
    VCP[V_LAST_LOW]=detector.last_low;
    VCP[V_LAST_HIGH]=detector.last_high;
    VCP[V_REQUEST]=detector.request;
    VCP[V_REQUEST_CYCLE]=detector.request_cycle;
    VCP[V_INITIAL_LEVEL]=initial_level;
    VCP[V_FINAL_LEVEL]=!!(idr & VCP_PIN);
    VCP[V_SOURCE_BITS]=sources;
    VCP[V_POLLS]=polls;
    VCP[V_MAGIC]=VCP_MAGIC;
    __DSB();
    if (reason!=NO_REQUEST) {
        /* Preserve the qualified PE1 branch's awake/cache/context policy. */
        SCB_DisableICache();
        recovery_gpio_park();
    }
}

void recovery_gpio_publish(void)
{
    /* Normal path only, after raw10_memory_init; capture overwrites low SRAM. */
    PUBLISHED[G_MAGIC]=0U;
    for (uint32_t i=1U; i<GUARD_WORDS; ++i) PUBLISHED[i]=GUARD[i];
    VCP_PUBLISHED[V_MAGIC]=0U;
    for (uint32_t i=1U; i<VCP_WORDS; ++i) VCP_PUBLISHED[i]=VCP[i];
    __DSB();
    PUBLISHED[G_MAGIC]=GUARD[G_MAGIC];
    VCP_PUBLISHED[V_MAGIC]=VCP[V_MAGIC];
    __DSB();
}
