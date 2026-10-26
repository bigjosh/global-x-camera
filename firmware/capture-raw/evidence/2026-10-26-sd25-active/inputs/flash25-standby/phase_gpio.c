/* One-wire phase observations, separate from the qualified camera baseline.
 * Idle LOW; event 1..10 is a HIGH pulse of event * 800 nominal 400 MHz cycles.
 * No timer configuration, global clock changes, or persistent storage access.
 * A disabled/stalled counter gives a missing/invalid pulse, never an infinite
 * wait. The external decoder must reject incomplete or malformed sequences.
 */
#include "stm32n6xx.h"
#include "phase_gpio.h"
#define PHASE_PIN (1U << 12)
#define PHASE_PAIR (3U << 24)
#define PHASE_POLL_LIMIT 4096U

__attribute__((noinline)) int phase_gpio_init(void)
{
    if (!(DWT->CTRL & DWT_CTRL_CYCCNTENA_Msk) ||
        !(CoreDebug->DEMCR & CoreDebug_DEMCR_TRCENA_Msk)) return 0;
    RCC->AHB4ENSR = RCC_AHB4ENSR_GPIODENS;
    __DSB();
    if (!(RCC->AHB4ENR & RCC_AHB4ENR_GPIODEN) ||
        (RCC->AHB4RSTR & RCC_AHB4RSTR_GPIODRST)) return 0;
    GPIOD->BSRR = PHASE_PIN << 16;
    GPIOD->OTYPER &= ~PHASE_PIN;
    GPIOD->OSPEEDR = (GPIOD->OSPEEDR & ~PHASE_PAIR) | (1U << 24);
    GPIOD->PUPDR &= ~PHASE_PAIR;
    GPIOD->MODER = (GPIOD->MODER & ~PHASE_PAIR) | (1U << 24);
    __DSB();
    return 1;
}

__attribute__((noinline)) int phase_gpio_emit(uint32_t event)
{
    if (event < 1U || event > 10U ||
        !(DWT->CTRL & DWT_CTRL_CYCCNTENA_Msk)) return 0;
    uint32_t saved = __get_PRIMASK();
    __disable_irq();
    GPIOD->BSRR = PHASE_PIN;
    __DSB();
    uint32_t start = DWT->CYCCNT;
    uint32_t polls = PHASE_POLL_LIMIT;
    while ((uint32_t)(DWT->CYCCNT - start) < event * 800U && --polls) {
        __NOP();
    }
    GPIOD->BSRR = PHASE_PIN << 16;
    __DSB();
    __set_PRIMASK(saved);
    return polls != 0U;
}
