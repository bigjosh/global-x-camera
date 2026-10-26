#ifndef GLOBAL_X_RAW_ERROR_CODES_H
#define GLOBAL_X_RAW_ERROR_CODES_H

#include <stdint.h>
#include "sd_card.h"
#include "magic_slots.h"

/* Product codes 1..7 are settled; 8 is the explicit prototype fallback for
 * an internal firmware/guard failure. Merely rendering codes 1 or 6 does not
 * implement battery sensing or an allocation-index integrity detector. */
enum raw_error_blink {
    RAW_ERROR_NONE=0U,
    RAW_ERROR_LOW_BATTERY=1U,
    RAW_ERROR_CAMERA_INIT=2U,
    RAW_ERROR_FRAME=3U,
    RAW_ERROR_STORAGE=4U,
    RAW_ERROR_SAVE=5U,
    RAW_ERROR_INDEX=6U,
    RAW_ERROR_FULL=7U,
    RAW_ERROR_INTERNAL=8U
};

/* Pure classifier for the RAW magic-slot coordinator's terminal records.
 * It grants no cleanup, idle, recovery or shutdown permission. Callers with
 * a directly known cause may retain an explicit category before cleanup.
 * In particular result 1/2 can also be SD argument/state codes, but the raw
 * coordinator uses them for request/context refusal; disambiguate a cleanup
 * error at its call site rather than guessing from these two values.
 *
 * Unknown/torn slot markers are occupied, not automatically index damage.
 * Consequently the current format has no inferred code-6 case here. */
static inline uint32_t raw_error_blink_code(uint32_t result,
    uint32_t capture_where,uint32_t capture_fault,uint32_t sd_error,
    uint32_t slot_error,uint32_t armed)
{
    if(!result) return RAW_ERROR_NONE;
    if(result>=0xF000U || result<3U) return RAW_ERROR_INTERNAL;

    if((result&0xFF00U)==0x0600U) {
        uint32_t where=capture_where?capture_where:(result&255U);
        if(where==0xAFU || where==0x7FFFU || where==0xFFU)
            return RAW_ERROR_INTERNAL; /* late-loader/assertion, not camera */
        /* START acknowledgement/state checks still describe initialization,
         * even though the receiver was armed before checking them. */
        if(where==0x75U || where==0x76U) return RAW_ERROR_CAMERA_INIT;
        return armed?RAW_ERROR_FRAME:RAW_ERROR_CAMERA_INIT;
    }
    if((result&0xFF00U)==0x0100U) return RAW_ERROR_CAMERA_INIT;
    if((result&0xFF00U)==0x0500U) return RAW_ERROR_FRAME;
    if((result&0xFF00U)==0x0200U) return RAW_ERROR_STORAGE;

    if((result&0xFFF0U)==0x0330U ||
       (result&0xFFF0U)==0x0340U) {
        /* A stopped producer can surface as a failed storage call. Preserve
         * its camera cause instead of reporting an SD-write failure. */
        if(capture_fault || sd_error==SD_ERR_PRODUCER) return RAW_ERROR_FRAME;
        return RAW_ERROR_SAVE;
    }
    if((result&0xFFF0U)==0x0320U) {
        if(slot_error==MAGIC_SLOTS_ERR_FULL) return RAW_ERROR_FULL;
        if(slot_error==MAGIC_SLOTS_ERR_IO) return RAW_ERROR_STORAGE;
        return RAW_ERROR_INTERNAL;
    }
    if(result>=0x0300U && result<0x0320U) {
        /* SCR OR-encoded errors 16..22 overlap the slot-open 0x310 range.
         * A latched slot error distinguishes actual geometry/state refusal. */
        return slot_error?RAW_ERROR_INTERNAL:RAW_ERROR_STORAGE;
    }
    /* Bare SD errors follow the completed operation's deinitialization.
     * Values outside the current driver enum are not guessed to be I/O. */
    if(result<=SD_ERR_PRODUCER) {
        if(capture_fault || sd_error==SD_ERR_PRODUCER) return RAW_ERROR_FRAME;
        return RAW_ERROR_SAVE;
    }
    return RAW_ERROR_INTERNAL;
}

#endif
