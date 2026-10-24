/* Prototype completion sleep. Preserve SRAM, rails, debug clocks and recovery.
 * This is ordinary CPU WFI sleep, NOT the final regulator-off shutdown state. */
#include "status_leds.h"
#include "phase_gpio.h"

__attribute__((noreturn, noinline, used)) void status_led_complete_sleep(void)
{
    status_led_set(STATUS_LED_OFF);
    __disable_irq();
    SysTick->CTRL = 0U;
    SysTick->VAL = 0U;
    unsigned banks = (ICB->ICTR & ICB_ICTR_INTLINESNUM_Msk) + 1U;
    for (unsigned i = 0U; i < banks; ++i) {
        NVIC->ICER[i] = 0xFFFFFFFFU;
        NVIC->ICPR[i] = 0xFFFFFFFFU;
    }
    SCB->ICSR = SCB_ICSR_PENDSTCLR_Msk | SCB_ICSR_PENDSVCLR_Msk;
    SCB->SCR &= ~(SCB_SCR_SLEEPDEEP_Msk | SCB_SCR_SLEEPONEXIT_Msk);
    __DSB(); __ISB();
    uint32_t enabled = 0U, pending = 0U;
    for (unsigned i = 0U; i < banks; ++i) {
        enabled |= NVIC->ISER[i];
        pending |= NVIC->ISPR[i];
    }
    STATUS_LED_PROOF[LED_P_PHASE] = STATUS_LED_OFF;
    status_led_proof_sample(LED_P_SLEEP_CYCLE);
    STATUS_LED_PROOF[LED_P_SCR] = SCB->SCR;
    STATUS_LED_PROOF[LED_P_PRIMASK] = __get_PRIMASK();
    STATUS_LED_PROOF[LED_P_SYSTICK_CTRL] = SysTick->CTRL;
    STATUS_LED_PROOF[LED_P_ICSR] = SCB->ICSR;
    STATUS_LED_PROOF[LED_P_NVIC_ENABLE_OR] = enabled;
    STATUS_LED_PROOF[LED_P_NVIC_PENDING_OR] = pending;
    STATUS_LED_PROOF[LED_P_SLEEP_STATE] = 2U; /* Prepared for the awake diagnostic completion park. */
    __DSB(); __ISB();
    (void)phase_gpio_emit(10U);
  __asm volatile(".global status_led_sleep_idle\n"
                   "status_led_sleep_idle:\n"
                   "nop\n"
                   "b.n status_led_sleep_idle\n");
    __builtin_unreachable();
}
