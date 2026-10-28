#ifndef CAPTURE_RAW_PRODUCER_H
#define CAPTURE_RAW_PRODUCER_H
#include <stdint.h>

/* Optional experimental LINE watermark. A 64-line holdback is deliberately
 * retained; CPU barriers alone do not prove DMA writes have reached SRAM.
 * FRAME + complete image validation is authoritative for the final bytes.
 * The complete linear frame remains allocated; this is not a wrapping FIFO.
 */
#define RAW_PRODUCER_MAGIC 0x50524431U
#define RAW_PRODUCER_BYTES 1909600U
#define RAW_PRODUCER_HEIGHT 1364U
#define RAW_PRODUCER_ROW_BYTES 1400U
#define RAW_PRODUCER_GROUP_LINES 64U
#define RAW_PRODUCER_GROUP_BYTES 89600U
#define RAW_PRODUCER_FULL_GROUPS 21U
#define RAW_PRODUCER_MAX_LINE_EVENTS 22U
#define RAW_PRODUCER_LOG_CAPACITY 24U
#define RAW_PRODUCER_SNAPSHOT_BYTES 512U
#define RAW_PRODUCER_SNAPSHOT_ADDRESS 0x343D0000U
#define RAW_PRODUCER_SNAPSHOT_CAPACITY 20U

enum { RAW_PRODUCER_ERR_LINES=1U, RAW_PRODUCER_ERR_FRAME=2U,
       RAW_PRODUCER_ERR_CAPTURE=4U, RAW_PRODUCER_ERR_ARGUMENT=8U };
typedef void (*raw_producer_snapshot_t)(uint32_t index,uint32_t offset,uint32_t count);

typedef struct raw_producer {
    uint32_t magic, schema, enabled, line_events;
    uint32_t frame_seen, validated, error, available_bytes;
    uint32_t first_line_cycle, first_prefix_cycle, last_line_cycle, frame_cycle;
    uint32_t validation_cycle, max_prefinal_bytes, ignored_after_frame, snapshot_count;
    /* Each observed pre-FRAME LINE event logs cycle then published bytes. */
    uint32_t events[RAW_PRODUCER_LOG_CAPACITY][2];
    /* Each optional completed snapshot logs original byte offset and bytes. */
    uint32_t snapshots[RAW_PRODUCER_SNAPSHOT_CAPACITY][2];
} raw_producer_t;

extern volatile raw_producer_t raw_producer;
void raw_producer_init(volatile raw_producer_t *p,uint32_t enabled);
/* ISR-only publication. Snapshot, when provided, is called BEFORE the new
 * prefix is published. It must copy the requested immutable diagnostic range
 * synchronously, cannot sleep, and cannot call any SD API. */
void raw_producer_line(volatile raw_producer_t *p,uint32_t cycle,
                       raw_producer_snapshot_t snapshot);
/* Freeze line publication at the first FRAME event, including when the HAL
 * invokes FRAME before LINE from the same status snapshot. No tail is released
 * here; the consumer still needs complete() after full-frame checks. */
void raw_producer_frame(volatile raw_producer_t *p,uint32_t cycle);
void raw_producer_fault(volatile raw_producer_t *p,uint32_t error);
/* Caller must run this only after frame-end byte count and camera/guard checks
 * at a safe driver-call boundary. Returns 0 on success, error otherwise. */
uint32_t raw_producer_complete(volatile raw_producer_t *p,uint32_t bytes,
    uint32_t frames,uint32_t errors,uint32_t canary,uint32_t cycle);
uint32_t raw_producer_available(const volatile raw_producer_t *p);
/* Pure consumer bound. Returns only available whole sectors, clamped to the
 * 3729 full-sector payload prefix; final352 bytes always use slots_finish. */
uint32_t raw_producer_next(const volatile raw_producer_t *p,
                          uint32_t submitted_sectors,uint32_t max_sectors);
#endif
