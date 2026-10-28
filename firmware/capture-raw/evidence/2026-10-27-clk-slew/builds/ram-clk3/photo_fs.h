#ifndef CAMERA_PHOTO_FS_H
#define CAMERA_PHOTO_FS_H
#include <stddef.h>
#include <stdint.h>
#include "sd_card.h"

enum {
    PHOTO_FS_OK=0, PHOTO_FS_ERROR=-1, PHOTO_FS_FULL=-2,
    PHOTO_FS_BAD_STATE=-3, PHOTO_FS_BAD_ARGUMENT=-4,
    PHOTO_FS_WRONG_FORMAT=-5, PHOTO_FS_UNSAFE_MEDIA=-6
};
enum {
    PHOTO_FS_STATE_NONE, PHOTO_FS_STATE_MOUNTED, PHOTO_FS_STATE_OPEN,
    PHOTO_FS_STATE_FINISHED, PHOTO_FS_STATE_ABORTED, PHOTO_FS_STATE_ERROR
};
enum {
    PHOTO_FS_STAGE_NONE, PHOTO_FS_STAGE_BIND, PHOTO_FS_STAGE_MOUNT,
    PHOTO_FS_STAGE_FORMAT, PHOTO_FS_STAGE_SPACE, PHOTO_FS_STAGE_NAME,
    PHOTO_FS_STAGE_OPEN, PHOTO_FS_STAGE_WRITE, PHOTO_FS_STAGE_SYNC_FILE,
    PHOTO_FS_STAGE_CLOSE, PHOTO_FS_STAGE_SYNC_CARD, PHOTO_FS_STAGE_RENAME,
    PHOTO_FS_STAGE_ABORT, PHOTO_FS_STAGE_READBACK
};
typedef struct {
    uint32_t state, stage, fat_result, bytes_written, expected_max_bytes;
    uint32_t file_number, cluster_bytes, free_clusters, completed;
    uint64_t sector_count;
    char final_name[13], temporary_name[13];
} photo_fs_report_t;

/* Single static filesystem/file context; caller serializes all access.
 * sd_init must have succeeded. Mount NEVER formats on any failure. */
int photo_fs_mount(sd_card_t *card);
/* Explicit destructive operation: new MBR with one FAT32 partition, two FATs,
 * 32 KiB clusters. Never called automatically from mount/open/save. */
int photo_fs_format(sd_card_t *card);
/* Requires conservative maximum final PNG length; reserves no clusters.
 * Existing PNG and TMP names are skipped. All writes use FA_CREATE_NEW. */
int photo_fs_open(uint32_t expected_max_bytes);
int photo_fs_append(const void *data, size_t bytes);
/* png16_write_fn adapter: returns 1 only after accepting every byte, else 0.
 * All other photo_fs operations return PHOTO_FS_OK (zero) on success. */
int photo_fs_write_callback(void *context, const uint8_t *data, size_t bytes);
/* sync file -> close -> card ready -> rename TMP to PNG -> card ready.
 * Success is not a power-loss atomicity guarantee. */
int photo_fs_finish(void);
/* Closes when safe but preserves TMP; never deletes any existing file. */
int photo_fs_abort(void);
/* Reads an existing generated PNG/TMP name; never opens for writing.
 * No active save may be open. Caller provides bounded output buffer. */
int photo_fs_readback(const char *name, uint32_t offset, void *buffer,
                      uint32_t capacity, uint32_t *bytes_read);
const photo_fs_report_t *photo_fs_get_report(void);
#endif
