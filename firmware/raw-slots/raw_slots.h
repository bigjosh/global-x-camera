#ifndef GLOBAL_X_RAW_SLOTS_H
#define GLOBAL_X_RAW_SLOTS_H

#include <stdint.h>
#include "../sd-storage/sd_card.h"

/* On-media v1: one 512-byte header followed by 3730 payload sectors.
 * No FAT, image conversion, on-card cache, implicit formatting or overwrite.
 * A card must be explicitly formatted once. Open/scan reject unknown headers.
 * All APIs are synchronous and have one owner; no call is interrupt-safe.
 */
#define RAW_SLOTS_VERSION 1U
#define RAW_SLOTS_FIRST_LBA 8U
#define RAW_SLOTS_STRIDE 3731U
#define RAW_SLOTS_WIDTH 1120U
#define RAW_SLOTS_HEIGHT 1364U
#define RAW_SLOTS_ROW_BYTES 1400U
#define RAW_SLOTS_PAYLOAD_BYTES 1909600U
#define RAW_SLOTS_PAYLOAD_SECTORS 3730U
#define RAW_SLOTS_WHOLE_SECTORS 3729U
#define RAW_SLOTS_TAIL_BYTES 352U
#define RAW_SLOTS_PADDED_BYTES (RAW_SLOTS_PAYLOAD_SECTORS*SD_SECTOR_BYTES)
#define RAW_SLOTS_PACKING_MIPI_RAW10 1U
#define RAW_SLOTS_FREE 0x45455246U
#define RAW_SLOTS_PARTIAL 0x54524150U
#define RAW_SLOTS_FULL 0x4C4C5546U
#define RAW_SLOTS_NO_SLOT 0xFFFFFFFFU
#define RAW_SLOTS_META_TIME_VALID (1U<<0)
#define RAW_SLOTS_META_EXPOSURE_VALID (1U<<1)
#define RAW_SLOTS_META_GAINS_VALID (1U<<2)
#define RAW_SLOTS_META_ORIENTATION_VALID (1U<<3)

enum raw_slots_error {
    RAW_SLOTS_OK=0, RAW_SLOTS_ERR_ARGUMENT, RAW_SLOTS_ERR_IO,
    RAW_SLOTS_ERR_VOLUME, RAW_SLOTS_ERR_FORMATTING, RAW_SLOTS_ERR_HEADER,
    RAW_SLOTS_ERR_CAPACITY, RAW_SLOTS_ERR_FULL, RAW_SLOTS_ERR_STATE,
    RAW_SLOTS_ERR_LENGTH, RAW_SLOTS_ERR_GENERATION, RAW_SLOTS_ERR_VERIFY
};

typedef struct raw_slots_metadata {
    uint64_t capture_id;
    uint64_t timestamp_us; /* Valid only when metadata_flags bit 0 is set. */
    uint32_t exposure_us;
    uint32_t analog_gain_milli;
    uint32_t digital_gain_milli;
    uint32_t orientation; /* Application value; 0xffffffff = unavailable. */
    uint32_t metadata_flags;
} raw_slots_metadata_t;

typedef int (*raw_slots_writer_t)(sd_card_t *,uint32_t,const void *,uint32_t);

typedef struct raw_slots {
    sd_card_t *card;
    /* Optional direct payload transport, e.g. sd_write_blocks_dma.
     * Set after open/format. NULL uses sd_write_blocks. Metadata always uses
     * sd_write_blocks; the writer must complete synchronously and propagate
     * SD driver errors/ownership exactly like that function. */
    raw_slots_writer_t write_payload;
    uint64_t generation;
    uint32_t slot_count, selected_slot, payload_lba, written_sectors;
    uint32_t opened, active, selected_valid, error;
    uint32_t scan_headers, formatted_slots, read_sectors, write_sectors;
    raw_slots_metadata_t metadata;
    uint32_t io[128] __attribute__((aligned(32)));
} raw_slots_t;

/* Both calls initialize fs. Format is destructive and never implicit.
 * generation is a nonzero 64-bit nonce supplied as two words. It must differ
 * from any readable prior format generation. slot_limit=0 uses all capacity;
 * a nonzero limit is useful for bounded commissioning tests. After successful
 * full-capacity commissioning, use 0 for the final format.
 * Format publishes FORMATTING, syncs and verifies it before touching headers;
 * READY is published only after every FREE header has completed. Progress is
 * visible in formatted_slots and sd_progress() is serviced for every slot.
 */
int raw_slots_open(raw_slots_t *fs, sd_card_t *card);
int raw_slots_format(raw_slots_t *fs, sd_card_t *card,
                     uint32_t generation_lo, uint32_t generation_hi,
                     uint32_t slot_limit);
/* Scan from slot zero, skipping valid FULL/PARTIAL headers. Invalid, blank or
 * foreign-generation headers are errors, never FREE. No data is erased. */
int raw_slots_find_free(raw_slots_t *fs);
/* Writes PARTIAL before any payload. Metadata may be NULL for unknown values. */
int raw_slots_begin(raw_slots_t *fs, const raw_slots_metadata_t *metadata);
/* Direct writes of already-produced whole sectors, max total 3729. Buffer
 * lifetime/visibility/alignment are the caller's responsibility (32-byte
 * alignment recommended for IDMA); no pixel copy or CRC scan occurs here.
 * Counts can exceed SD_MAX_TRANSFER_SECTORS; the transport chunks as needed. */
int raw_slots_append(raw_slots_t *fs, const void *buffer, uint32_t count);
/* Requires exactly 3729 whole sectors already appended; copies the remaining
 * 352 bytes to an aligned sector with 160 zero pad bytes. Fresh card ready is
 * required before FULL, and again after the FULL header. A failed call never
 * authorizes shutdown: independently establish card idle with sd_sync/deinit.
 * Protocol ready is not qualification against sudden power loss in the FTL. */
int raw_slots_finish(raw_slots_t *fs, const void *tail352);
/* Opt-in whole-image transport. The caller owns a contiguous 3730-sector
 * buffer whose last160 bytes are zero and whose camera writes have stopped.
 * Calls the explicitly selected payload writer exactly once. PARTIAL remains
 * until a separate commit, so the caller can finish sensor/guard checks first. */
int raw_slots_write_padded(raw_slots_t *fs, const void *buffer);
/* Commit only an exactly complete payload; performs fresh READY before FULL
 * and again after its separate metadata-sector write. */
int raw_slots_commit(raw_slots_t *fs);

#endif
