#ifndef CAPTURE_RAW_CYCLE_TRACE_H
#define CAPTURE_RAW_CYCLE_TRACE_H

#include <stdint.h>

#ifndef RAW_CYCLE_TRACE
#define RAW_CYCLE_TRACE 0
#endif

/* Dedicated high-SRAM diagnostic area: initialize only after its banks are
 * enabled. CYCCNT must already be running at the unchanged nominal 400 MHz.
 * This record does not survive Standby and is not a storage-idle proof.
 */
#define CYCLE_TRACE_ADDRESS 0x343FB000U
#define CYCLE_TRACE_WORDS 256U
#define CYCLE_TRACE_MAGIC 0x314C5443U /* CTL1 */
#define CYCLE_TRACE_SCHEMA 1U
#define CYCLE_TRACE_HZ 400000000U
#define CYCLE_TRACE_DONE 0x454E4F44U /* DONE */
#define CYCLE_TRACE_UNSET 0xFFFFFFFFU
#define CYCLE_TRACE_EVENT_WORD 32U
#define CYCLE_TRACE_EVENT_COUNT 128U
#define CYCLE_TRACE_COUNTER_WORD 160U
#define CYCLE_TRACE_COUNTER_COUNT 32U

#if RAW_CYCLE_TRACE
#include "cycle_trace_events.h"
#include "cycle_trace_sd.h"

/* Every event has a fixed address. Repeated use deliberately retains the last
 * occurrence; assign separate first/last IDs when both matter. There is no
 * append index, function call, printf, peripheral dump or per-event barrier.
 * Each slot/counter must have one writer (main or ISR), never both.
 */
#define CYCLE_MARK(name) do { \
    *(volatile uint32_t *)(CYCLE_TRACE_ADDRESS + \
        4U * (CYCLE_TRACE_EVENT_WORD + CTE_##name)) = \
        *(volatile uint32_t *)0xE0001004U; \
} while (0)
#define CYCLE_COUNT(name) do { \
    ++*(volatile uint32_t *)(CYCLE_TRACE_ADDRESS + \
        4U * (CYCLE_TRACE_COUNTER_WORD + CTC_##name)); \
} while (0)

static inline __attribute__((always_inline)) void cycle_trace_init(void)
{
    volatile uint32_t *const p = (volatile uint32_t *)CYCLE_TRACE_ADDRESS;
    const uint32_t start = *(volatile uint32_t *)0xE0001004U;
    for (uint32_t i = 0; i < CYCLE_TRACE_WORDS; ++i) p[i] = CYCLE_TRACE_UNSET;
    for (uint32_t i = 0; i < CYCLE_TRACE_COUNTER_COUNT; ++i)
        p[CYCLE_TRACE_COUNTER_WORD + i] = 0U;
    p[1] = CYCLE_TRACE_SCHEMA;
    p[2] = CYCLE_TRACE_WORDS;
    p[3] = CYCLE_TRACE_HZ;
    p[5] = start;
    p[7] = CYCLE_TRACE_EVENT_COUNT;
    p[8] = CYCLE_TRACE_COUNTER_COUNT;
    p[0] = CYCLE_TRACE_MAGIC;
}

/* Call only after the final event. The barrier and DONE publication belong to
 * finalization, not the fast hooks. A read before DONE is a partial record.
 * Completion means the caller finished logging; its result and independent
 * capture/storage terminal proofs still decide success and maintenance safety.
 */
static inline __attribute__((always_inline)) void cycle_trace_finish(uint32_t result)
{
    volatile uint32_t *const p = (volatile uint32_t *)CYCLE_TRACE_ADDRESS;
    p[6] = *(volatile uint32_t *)0xE0001004U;
    p[4] = result;
    __asm__ volatile ("dsb sy" ::: "memory");
    p[9] = CYCLE_TRACE_DONE;
}
#else
#define CYCLE_MARK(name) ((void)0)
#define CYCLE_COUNT(name) ((void)0)
static inline void cycle_trace_init(void) {}
static inline void cycle_trace_finish(uint32_t result) { (void)result; }
#endif
#endif
