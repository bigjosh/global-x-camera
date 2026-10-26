#ifndef RAW_ERROR_SIGNAL_H
#define RAW_ERROR_SIGNAL_H

#include <stdint.h>

enum error_signal_code {
    ERROR_SIGNAL_LOW_BATTERY = 1U, /* Reserved until a battery detector exists. */
    ERROR_SIGNAL_CAMERA_INIT = 2U,
    ERROR_SIGNAL_CAMERA_CAPTURE = 3U,
    ERROR_SIGNAL_STORAGE_INIT = 4U,
    ERROR_SIGNAL_STORAGE_WRITE = 5U,
    ERROR_SIGNAL_STORAGE_METADATA = 6U,
    ERROR_SIGNAL_STORAGE_FULL = 7U,
    ERROR_SIGNAL_INTERNAL = 8U
};

#define ERROR_SIGNAL_SETS 5U
#define ERROR_SIGNAL_ON_MS 100U
#define ERROR_SIGNAL_OFF_MS 400U
#define ERROR_SIGNAL_SET_GAP_MS 2000U

/* Failure-only terminal policy, separate from successful-save qualification.
 * No global data or expanded SRAM is needed, so the ROM-loaded prefix can use
 * it before the checked receiver/late code exists. It abandons the failed
 * capture/storage transaction; it never claims the card was idle or saved.
 * Reset plus the unchanged early UART guard remains the recovery mechanism.
 * Deep-mode precondition failure falls back to LEDs-off, masked shallow WFI.
 */
#if RAW_ERROR_PREFIX
/* The receiver's early range calls the separately ROM-loaded prefix engine.
 * Its fixed section address and complete bytes are verified by the builder. */
static inline __attribute__((noreturn)) void error_signal_shutdown(uint32_t code)
{
    ((void (*)(uint32_t))0x34181841U)(code);
    __builtin_unreachable();
}
#else
__attribute__((noreturn)) void error_signal_shutdown(uint32_t code);
#endif

#endif
