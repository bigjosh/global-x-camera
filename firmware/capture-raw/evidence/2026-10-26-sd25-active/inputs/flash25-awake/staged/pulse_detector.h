/* Pure integer detector shared by the target prefix and native offline tests.
 * Three complete 1 Mbaud zero-byte low pulses are a recovery request. A static
 * level, a single edge, or the unobserved first half of a low pulse is not.
 * Times are nominal 400 MHz DWT cycles; this is not a PVT timing guarantee.
 */
#ifndef RECOVERY_VCP_PULSE_DETECTOR_H
#define RECOVERY_VCP_PULSE_DETECTOR_H
#include <stdint.h>

#define VCP_WINDOW_CYCLES 40000U
#define VCP_MIN_LOW_CYCLES 2400U
#define VCP_MAX_LOW_CYCLES 5200U
#define VCP_MIN_HIGH_CYCLES 100U
#define VCP_MAX_HIGH_CYCLES 1600U
#define VCP_REQUIRED_PULSES 3U

typedef struct {
    uint32_t last_level, saw_high, low_started, falling, rising;
    uint32_t train, max_train, good_pulses, bad_pulses, edges;
    uint32_t last_low, last_high, request, request_cycle, first_cycle;
} recovery_vcp_detector;

static inline void recovery_vcp_init(recovery_vcp_detector *d,
                                     uint32_t now, uint32_t level)
{
    *d=(recovery_vcp_detector){0};
    d->last_level=!!level;
    d->saw_high=!!level;
    d->first_cycle=now;
}

static inline void recovery_vcp_sample(recovery_vcp_detector *d,
                                       uint32_t now, uint32_t level)
{
    level=!!level;
    if (level==d->last_level) return;
    d->last_level=level;
    ++d->edges;
    if (!level) {
        d->low_started=d->saw_high;
        d->falling=now;
        if (d->train) {
            d->last_high=(uint32_t)(now-d->rising);
            if (d->last_high<VCP_MIN_HIGH_CYCLES ||
                d->last_high>VCP_MAX_HIGH_CYCLES) d->train=0U;
        }
    } else {
        if (d->low_started) {
            d->last_low=(uint32_t)(now-d->falling);
            if (d->last_low>=VCP_MIN_LOW_CYCLES &&
                d->last_low<=VCP_MAX_LOW_CYCLES) {
                ++d->good_pulses;
                ++d->train;
                if (d->train>d->max_train) d->max_train=d->train;
                if (!d->request && d->train>=VCP_REQUIRED_PULSES) {
                    d->request=1U;
                    d->request_cycle=now;
                }
            } else {
                ++d->bad_pulses;
                d->train=0U;
            }
        }
        d->low_started=0U;
        d->saw_high=1U;
        d->rising=now;
    }
}
#endif
