#ifndef GX_PTP_PHOTO_STORE_H
#define GX_PTP_PHOTO_STORE_H

#include <stddef.h>
#include <stdint.h>
#include "../../raw-slots/magic_slots.h"

/* Portable, synchronous, one-owner backend. No allocation and no hardware
 * access outside the supplied callbacks. All callbacks return 1 on success.
 * read/write must complete their entire range; failed read bytes are untrusted.
 * write must finish card busy before returning. sync must freshly prove idle.
 * recover may restore an idle transport after a failed read, never reset while
 * a transfer remains active. A missing/failed recover stops further card I/O.
 * service may service USB/cancellation, but MUST NOT reenter this backend/SD.
 * A zero service result cancels at the next completed transfer boundary.
 */
#define PHOTO_STORE_IO_SECTORS 32U
#define PHOTO_STORE_BUFFER_BYTES MAGIC_SLOTS_PADDED_BYTES
#define PHOTO_STORE_PNG_ROW_BYTES (1U + MAGIC_SLOTS_WIDTH * 2U)
#define PHOTO_STORE_EXIF_BYTES 556U
#define PHOTO_STORE_COMMENT_BYTES 512U
#define PHOTO_STORE_PNG_BYTES (8U + 25U + 13U + 12U + PHOTO_STORE_EXIF_BYTES + \
    12U + 2U + MAGIC_SLOTS_HEIGHT * (5U + PHOTO_STORE_PNG_ROW_BYTES) + 4U + 12U)

enum photo_result {
    PHOTO_OK = 0, PHOTO_ARGUMENT = -1, PHOTO_IO = -2,
    PHOTO_NOT_FOUND = -3, PHOTO_UNSUPPORTED = -4, PHOTO_CANCELLED = -5,
    PHOTO_CHANGED = -6, PHOTO_WRITE_FAILED = -7
};
enum photo_flags {
    PHOTO_PREFIX_VALID = 1U, PHOTO_TRAILER_CHECKED = 2U,
    PHOTO_TRAILER_VALID = 4U, PHOTO_READ_ERROR = 8U,
    PHOTO_UNREADABLE_SECTORS = 16U, PHOTO_LEGACY = 32U,
    PHOTO_PARTIAL = 64U
};
typedef struct {
    void *user;
    int (*read)(void *, uint32_t lba, void *, uint32_t sectors);
    int (*write)(void *, uint32_t lba, const void *, uint32_t sectors);
    int (*sync)(void *);
    int (*recover)(void *);
    int (*service)(void *);
} photo_io_t;
typedef struct {
    uint32_t handle, slot_index, slot_lba, start_magic, image_offset;
    uint32_t flags, read_errors, unreadable_sectors, first_bad_lba;
    uint8_t metadata[MAGIC_SLOTS_METADATA_BYTES];
} photo_info_t;
typedef struct {
    photo_io_t io;
    uint32_t slot_count, erased_byte;
    uint32_t scanned_slots, known_objects, unknown_occupied, unreadable_headers;
    uint32_t scratch[PHOTO_STORE_IO_SECTORS * 128U];
} photo_store_t;
typedef int (*photo_visit_fn)(void *, const photo_info_t *);
typedef int (*photo_write_fn)(void *, const uint8_t *, size_t);

/* SCR DATA_STAT_AFTER_ERASE must supply erased_byte (0 or 255); this does not
 * format or establish commissioning. Ignore trailing non-slot sectors. */
int photo_store_open(photo_store_t *, const photo_io_t *, uint64_t sector_count,
                     uint32_t erased_byte);
/* Scan every slot, including beyond deletion holes; no payload reads. Unknown
 * occupied markers are counted and hidden, never reused. A failed header read
 * aborts with PHOTO_IO (no false complete catalogue). Each recognized object
 * has a stable handle slot_index+1; callback zero cancels the scan. */
int photo_store_scan(photo_store_t *, photo_visit_fn, void *);
/* Fresh first/last sector checks. Completion markers are NOT a pixel checksum.
 * Validated CKN1 settings are exported in the PNG comment; unknown metadata
 * remains opaque, and no date/orientation or calibrated ISO is inferred. */
int photo_store_info(photo_store_t *, uint32_t handle, photo_info_t *);
/* Fresh whole-slot read into caller's >=PHOTO_STORE_BUFFER_BYTES word-aligned
 * RAM. Failed bursts are retried sector-by-sector after recover. Unreadable
 * sectors become zero, never stale RAM, and flags/counters describe the loss.
 * PHOTO_OK can carry recovery warnings: inspect flags. The resulting buffer
 * is immutable until PNG transmission finishes. Cancellation gives no export.
 * 'info' must originate from this store's info/scan; checked again on entry.
 */
int photo_store_load(photo_store_t *, photo_info_t *, void *buffer, size_t bytes);
/* Explicit deletion of this single recognized photo. Clear sectors 1..3729
 * in reverse chunk order, sync, then clear header, sync, read it back. No CMD38
 * erase-group assumptions, no adjacent writes, no new journal. Interrupted
 * deletion can damage this requested photo; SD power-loss atomicity remains
 * unqualified. A cancellation before final header leaves the slot occupied.
 */
int photo_store_delete(photo_store_t *, uint32_t handle);
int photo_store_is_recovered(const photo_info_t *);
/* Slot-derived name, not a capture date. *_RECOVERED.png after known damage.
 * Returns required bytes excluding NUL, or PHOTO_ARGUMENT for a short buffer. */
int photo_store_filename(const photo_info_t *, char *, size_t);
/* Fixed-length valid grayscale16 PNG: sample<<6, sBIT=10, filter0, stored
 * DEFLATE per row, fixed eXIf/UserComment with warnings and checksum limits.
 * No image compression, tone correction, dates or orientation are fabricated.
 * The buffer must be a completed load result. row_scratch >=ROW_BYTES.
 * Callback receives <=ROW_BYTES bytes and must consume all or return zero.
 * Caller can service/cancel USB in the callback. Returns WRITE_FAILED on zero.
 */
int photo_store_png(const photo_info_t *, const void *buffer, size_t bytes,
                    uint8_t *row_scratch, size_t row_bytes,
                    photo_write_fn, void *);

#endif
