#ifndef STATUS_LEDS_H
#define STATUS_LEDS_H

#include <stdint.h>
#include "stm32n657xx.h"

/* MB1940: LD5 red PG10, LD6 green PG0, LD7 blue PG8; active low.
 * Restrict every GPIO update to those pins. No GPIOG reset is allowed. */
#define STATUS_LED_RED (1U << 10U)
#define STATUS_LED_GREEN (1U << 0U)
#define STATUS_LED_BLUE (1U << 8U)
#define STATUS_LED_MASK (STATUS_LED_RED | STATUS_LED_GREEN | STATUS_LED_BLUE)
#define STATUS_LED_MODE_MASK ((3U << 20U) | (3U << 0U) | (3U << 16U))
#define STATUS_LED_MODE_OUTPUT ((1U << 20U) | (1U << 0U) | (1U << 16U))

enum status_led_phase {
    STATUS_LED_OFF = 0U,
    STATUS_LED_BOOT = 1U,
    STATUS_LED_ACQUIRE = 2U,
    STATUS_LED_NAND_WRITE = 3U, /* Reserved until actual NAND writes exist. */
    STATUS_LED_ERROR = 4U
};

static inline void status_led_set(enum status_led_phase phase)
{
    uint32_t on = phase == STATUS_LED_BOOT || phase == STATUS_LED_ERROR ? STATUS_LED_RED :
                  phase == STATUS_LED_ACQUIRE ? STATUS_LED_BLUE :
                  phase == STATUS_LED_NAND_WRITE ? STATUS_LED_GREEN : 0U;
    GPIOG->BSRR = (STATUS_LED_MASK & ~on) | (on << 16U);
    __DSB();
}

/* Called at the beginning of stage1_main, before any expanded SRAM access.
 * ROM execution necessarily precedes this earliest application indication. */
static inline void status_led_boot_begin(void)
{
    RCC->AHB4ENSR = RCC_AHB4ENSR_GPIOGENS;
    (void)RCC->AHB4ENR;
    GPIOG->BSRR = STATUS_LED_MASK; /* All off before changing output modes. */
    GPIOG->OTYPER &= ~STATUS_LED_MASK;
    GPIOG->PUPDR &= ~STATUS_LED_MODE_MASK;
    GPIOG->OSPEEDR &= ~STATUS_LED_MODE_MASK;
    GPIOG->MODER = (GPIOG->MODER & ~STATUS_LED_MODE_MASK) | STATUS_LED_MODE_OUTPUT;
    status_led_set(STATUS_LED_BOOT);
}

/* Free diagnostic RAM: FAST ends 0x343f8880; shutdown 0x343f8900..893f;
 * ForceRx 0x343f8940..89bf. This 32-word block ends at 0x343f8a40.
 * Only call these helpers AFTER raw10_memory_init has powered that SRAM. */
#define STATUS_LED_PROOF ((volatile uint32_t *)0x343F89C0U)
#define STATUS_LED_PROOF_WORDS 32U
#define STATUS_LED_PROOF_MAGIC 0x4C454431U /* LED1 */
enum {
    LED_P_MAGIC, LED_P_SCHEMA, LED_P_WORDS, LED_P_PHASE,
    LED_P_RED_CYCLE, LED_P_RED_ODR, LED_P_RED_IDR,
    LED_P_BLUE_CYCLE, LED_P_BLUE_ODR, LED_P_BLUE_IDR,
    LED_P_OFF_CYCLE, LED_P_OFF_ODR, LED_P_OFF_IDR,
    LED_P_SLEEP_CYCLE, LED_P_SLEEP_ODR, LED_P_SLEEP_IDR,
    LED_P_MODER, LED_P_OTYPER, LED_P_OSPEEDR, LED_P_PUPDR,
    LED_P_SCR, LED_P_PRIMASK, LED_P_SYSTICK_CTRL, LED_P_ICSR,
    LED_P_SLEEP_STATE, LED_P_NVIC_ENABLE_OR, LED_P_NVIC_PENDING_OR,
    LED_P_AHB4ENR, LED_P_ERROR_CYCLE, LED_P_ERROR_ODR, LED_P_ERROR_IDR,
    LED_P_RESERVED
};

static inline void status_led_proof_sample(unsigned offset)
{
    STATUS_LED_PROOF[offset] = DWT->CYCCNT;
    STATUS_LED_PROOF[offset + 1U] = GPIOG->ODR;
    STATUS_LED_PROOF[offset + 2U] = GPIOG->IDR;
    __DMB();
}

static inline void status_led_proof_init(void)
{
    for (unsigned i = 0U; i < STATUS_LED_PROOF_WORDS; ++i) STATUS_LED_PROOF[i] = 0U;
    STATUS_LED_PROOF[LED_P_SCHEMA] = 1U;
    STATUS_LED_PROOF[LED_P_WORDS] = STATUS_LED_PROOF_WORDS;
    STATUS_LED_PROOF[LED_P_PHASE] = STATUS_LED_BOOT;
    status_led_proof_sample(LED_P_RED_CYCLE);
    STATUS_LED_PROOF[LED_P_MODER] = GPIOG->MODER;
    STATUS_LED_PROOF[LED_P_OTYPER] = GPIOG->OTYPER;
    STATUS_LED_PROOF[LED_P_OSPEEDR] = GPIOG->OSPEEDR;
    STATUS_LED_PROOF[LED_P_PUPDR] = GPIOG->PUPDR;
    STATUS_LED_PROOF[LED_P_AHB4ENR] = RCC->AHB4ENR;
    __DMB();
    STATUS_LED_PROOF[LED_P_MAGIC] = STATUS_LED_PROOF_MAGIC;
}

static inline void status_led_proof_phase(enum status_led_phase phase, unsigned offset)
{
    status_led_set(phase);
    STATUS_LED_PROOF[LED_P_PHASE] = phase;
    status_led_proof_sample(offset);
}

#endif
