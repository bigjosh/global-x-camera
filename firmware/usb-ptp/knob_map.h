/* Knob readings to sensor settings. Pure integer code with no hardware
 * access, so the same functions run in the selector and in native tests. */
#ifndef USB_PTP_KNOB_MAP_H
#define USB_PTP_KNOB_MAP_H

#include <stdint.h>
#include "knob_tables.h"

struct knob_setting {
    uint16_t lines;   /* manual coarse exposure, in sensor lines */
    uint16_t frame;   /* frame length, in sensor lines */
    uint8_t gain;     /* analog gain code: gain = 32 / (32 - code) */
};

/* Position across the usable travel, 0..1024, with a dead band at each end. */
static inline uint32_t knob_position(uint32_t code)
{
    if (code <= KNOB_CODE_LOW) return 0U;
    if (code >= KNOB_CODE_HIGH) return 1024U;
    return ((code - KNOB_CODE_LOW) * 1024U) / (KNOB_CODE_HIGH - KNOB_CODE_LOW);
}

/* Exponential in the knob position: equal turns give equal exposure ratios.
 * Linear interpolation between table points stays within about 1% of the
 * exact curve. */
static inline uint32_t knob_exposure(uint32_t code)
{
    uint32_t position = knob_position(code);
    uint32_t index = position >> 5, fraction = position & 31U;
    if (index >= KNOB_STEPS) return knob_exposure_lines[KNOB_STEPS];
    uint32_t low = knob_exposure_lines[index], high = knob_exposure_lines[index + 1U];
    return low + (((high - low) * fraction) >> 5);
}

/* Equal stops across the travel, rounded to the nearest table point. */
static inline uint32_t knob_gain(uint32_t code)
{
    uint32_t index = (knob_position(code) + 16U) >> 5;
    if (index > KNOB_STEPS) index = KNOB_STEPS;
    return knob_gain_codes[index];
}

/* The frame must outlast the exposure. Short exposures keep the frame length
 * the capture code has always used. */
static inline uint32_t knob_frame(uint32_t lines)
{
    uint32_t frame = lines + KNOB_FRAME_MARGIN;
    if (frame < KNOB_DEFAULT_FRAME) frame = KNOB_DEFAULT_FRAME;
    if (frame > KNOB_FRAME_MAX) frame = KNOB_FRAME_MAX;
    return frame;
}

static inline struct knob_setting knob_map(uint32_t exposure_code, uint32_t gain_code)
{
    struct knob_setting setting;
    uint32_t lines = knob_exposure(exposure_code);
    if (lines < KNOB_MIN_LINES) lines = KNOB_MIN_LINES;
    if (lines > KNOB_MAX_LINES) lines = KNOB_MAX_LINES;
    setting.lines = (uint16_t)lines;
    setting.frame = (uint16_t)knob_frame(lines);
    setting.gain = (uint8_t)knob_gain(gain_code);
    return setting;
}

/* Thumb-2 "MOVW r1, #value" (encoding T3) as the 32-bit word stored in
 * little-endian memory: first halfword in the low 16 bits. */
static inline uint32_t knob_movw_r1(uint32_t value)
{
    uint32_t first = 0xF240U | (((value >> 11) & 1U) << 10) | ((value >> 12) & 15U);
    uint32_t second = (((value >> 8) & 7U) << 12) | (1U << 8) | (value & 255U);
    return first | (second << 16);
}

#endif
