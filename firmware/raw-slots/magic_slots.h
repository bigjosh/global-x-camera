#ifndef GLOBAL_X_MAGIC_SLOTS_H
#define GLOBAL_X_MAGIC_SLOTS_H

#include <stdint.h>
#include "../sd-storage/sd_card.h"

/* Generation-free magic-slot format. All integers/markers are little endian.
 * A separately authorized whole-card erase establishes the initial free state.
 * No superblock, metadata sector, allocation table, commit rewrite or implicit
 * erase is performed here. Legacy raw_slots.h describes the older format. */
#define MAGIC_SLOTS_FIRST_LBA 0U
#define MAGIC_SLOTS_STRIDE 3730U
#define MAGIC_SLOTS_WIDTH 1120U
#define MAGIC_SLOTS_HEIGHT 1364U
#define MAGIC_SLOTS_ROW_BYTES 1400U
#define MAGIC_SLOTS_IMAGE_BYTES 1909600U
#define MAGIC_SLOTS_PREFIX_BYTES 4U
#define MAGIC_SLOTS_IMAGE_OFFSET MAGIC_SLOTS_PREFIX_BYTES
#define MAGIC_SLOTS_TRAILER_OFFSET (MAGIC_SLOTS_IMAGE_OFFSET+MAGIC_SLOTS_IMAGE_BYTES)
#define MAGIC_SLOTS_TRAILER_BYTES 4U
#define MAGIC_SLOTS_OBJECT_BYTES (MAGIC_SLOTS_TRAILER_OFFSET+MAGIC_SLOTS_TRAILER_BYTES)
#define MAGIC_SLOTS_PADDED_BYTES (MAGIC_SLOTS_STRIDE*SD_SECTOR_BYTES)
#define MAGIC_SLOTS_PADDING_BYTES (MAGIC_SLOTS_PADDED_BYTES-MAGIC_SLOTS_OBJECT_BYTES)
#define MAGIC_SLOTS_START_MAGIC 0x53525847U /* bytes GXRS */
#define MAGIC_SLOTS_END_MAGIC 0x45525847U   /* bytes GXRE */
#define MAGIC_SLOTS_NO_SLOT 0xFFFFFFFFU

enum magic_slots_error {
    MAGIC_SLOTS_OK=0, MAGIC_SLOTS_ERR_ARGUMENT, MAGIC_SLOTS_ERR_STATE,
    MAGIC_SLOTS_ERR_CAPACITY, MAGIC_SLOTS_ERR_IO, MAGIC_SLOTS_ERR_FULL,
    MAGIC_SLOTS_ERR_LENGTH, MAGIC_SLOTS_ERR_MARKER, MAGIC_SLOTS_ERR_NOT_IDLE
};

/* Exactly one invocation owns the selected whole-slot range. The writer may
 * wait for producer publication, but must not read unpublished bytes. Success
 * means all count sectors completed, fresh card readiness was observed, and
 * card->written_sectors increased by count. On failure the transport retains
 * its usual card/buffer ownership; this layer never resets or retries it. */
typedef int (*magic_slots_writer_t)(sd_card_t *card, uint32_t lba,
    const void *buffer, uint32_t count, void *context);

typedef struct magic_slots {
    sd_card_t *card;
    uint32_t slot_count, selected_slot, slot_lba, erased_byte;
    uint32_t opened, selected_valid, active, error;
    uint32_t scan_headers, read_sectors, written_sectors, write_sectors;
    uint32_t io[128] __attribute__((aligned(32)));
} magic_slots_t;

/* erased_byte MUST be 0x00 or 0xff obtained from the card's SCR
 * DATA_STAT_AFTER_ERASE; never infer it from arbitrary first-slot contents.
 * This call validates geometry only; it cannot prove commissioning succeeded.
 * Capacity is limited to 2^32 sectors and unused final sectors are not slots. */
int magic_slots_open(magic_slots_t *slots, sd_card_t *card, uint32_t erased_byte);
/* Read one complete sector per slot and examine exactly its first four bytes.
 * Only four copies of erased_byte are FREE. Any other word is occupied,
 * including unknown/torn magic; read failure stops allocation, never frees it.
 * Search starts at zero and returns the first FREE slot or ERR_FULL. */
int magic_slots_find_free(magic_slots_t *slots);
/* The caller has prepared GXRS at buffer[0..3]; image DMA may still be active.
 * The writer must withhold the final sector until frame validation and GXRE /
 * 152-byte zero padding preparation have completed. Buffer is word-aligned;
 * camera image destination buffer+4 separately must be 16-byte aligned.
 * This call performs no separate sector write and no full-frame software scan.
 * A successful return records 3730 written sectors and releases slot ownership.
 * Failure keeps active=1 if a write was attempted, even when transport is idle.
 * It never declares the slot FREE again or retries a partly written object. */
int magic_slots_write(magic_slots_t *slots, const void *buffer,
                      magic_slots_writer_t writer, void *context);

#endif
