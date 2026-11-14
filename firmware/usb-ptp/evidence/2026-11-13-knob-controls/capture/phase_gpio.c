/* PD12 is now D8 HOLD: no phase pulses may drive this pin LOW.
 * Keep the existing call interface and RAM instrumentation in its callers;
 * PD0 exposure mirroring is independent and remains unchanged. */
#include "phase_gpio.h"
__attribute__((noinline)) int phase_gpio_init(void) { return 1; }
__attribute__((noinline)) int phase_gpio_emit(uint32_t event)
{
    return event >= 1U && event <= 12U;
}
