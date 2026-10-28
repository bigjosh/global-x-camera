#ifndef PNG16_H
#define PNG16_H
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PNG16_MAX_WIDTH 1120U
#define PNG16_MAX_HEIGHT 1364U
#define PNG16_WORKSPACE_BYTES (192U * 1024U)
#define PNG16_MAX_CALLBACK_BYTES 16384U

typedef enum {
    PNG16_STORED_NONE = 0,
    PNG16_FAST_NONE = 1,
    PNG16_FAST_SUB = 2,
    /* Optional experiment: bytewise Sub + dynamic Huffman, no LZ matching.
     * Not the selected camera default; qualify total MCU/storage cost. */
    PNG16_HUFFMAN_SUB = 3
} png16_mode;

typedef enum {
    PNG16_OK = 0,
    PNG16_BAD_ARGUMENT = -1,
    PNG16_BAD_WORKSPACE = -2,
    PNG16_BAD_SAMPLE = -3,
    PNG16_WRITE_FAILED = -4,
    PNG16_COMPRESS_FAILED = -5
} png16_result;

/* Return nonzero only after accepting ALL bytes. Data is valid only during
 * this call. A failure stops encoding immediately; the output is incomplete.
 * This callback must not modify input/workspace or reenter the same workspace.
 */
typedef int (*png16_write_fn)(void *user, const uint8_t *data, size_t bytes);

/* Convenience static allocation with at least 8-byte alignment. It must live
 * outside the capture buffer, code, stack and diagnostics, never on the stack.
 * Alternatively allocate png16_workspace_size() suitably aligned bytes.
 */
typedef union {
    uint64_t alignment;
    uint8_t bytes[PNG16_WORKSPACE_BYTES];
} png16_workspace;

typedef struct {
    uint64_t output_bytes;   /* Successfully accepted callback bytes only. */
    uint32_t rows_encoded;
    uint32_t idat_chunks;
    uint32_t callback_calls; /* Includes a failing callback, if any. */
} png16_stats;

/* Optional profiling uses the caller's monotonically increasing, extended
 * 64-bit clock. Units are those returned by now(), normally CPU cycles. The
 * clock must not wrap, mutate encoder state, or reenter this encoder.
 *
 * The five component fields after total_cycles form its disjoint partition
 * when clock_error==0. DEFLATE includes compressor initialization and Adler32
 * (stored mode measures block construction plus Adler32 instead of compression);
 * framing includes PNG chunk CRCs and headers/trailers. Conversion includes
 * sample checking, endian/scaling conversion and the selected row filter.
 * Instrumentation overhead remains in the measured parent/other intervals;
 * these are instrumented elapsed times, not overhead-corrected pure CPU costs.
 * Failed encodes still publish partial timing after valid arguments.
 */
typedef struct {
    uint64_t total_cycles;
    uint64_t conversion_cycles;
    uint64_t deflate_cycles;
    uint64_t framing_cycles;
    uint64_t callback_cycles;
    uint64_t other_cycles;
    /* Nested evidence; do not add these to the partition above. */
    uint64_t deflate_inclusive_cycles;
    uint64_t deflate_output_cycles;
    uint64_t framing_inclusive_cycles;
    uint64_t framing_callback_cycles;
    uint32_t clock_calls;
    uint32_t clock_error; /* Bit 0: clock regressed; bit 1: accounting overflow/underflow. */
} png16_timing;

typedef struct {
    uint64_t (*now)(void *user);
    void *user;
    png16_timing *out;
} png16_timing_config;

size_t png16_workspace_size(void);
size_t png16_workspace_alignment(void);

/* Input is top-to-bottom RAW10, right-aligned in little-endian uint16 words.
 * Output is noninterlaced grayscale PNG16, sample<<6, network byte order,
 * sBIT=10. No gamma/black-level/tone conversion or sensor-bit truncation.
 * stride_bytes may include row padding. Input may be byte-unaligned.
 *
 * No allocation, filesystem, hardware, global mutable state or full-frame
 * copy. Validate dimensions/extent before writing. A bad sample discovered
 * later returns BAD_SAMPLE and leaves an incomplete stream; discard it.
 * Input must remain stable throughout encoding. Input and workspace must not
 * overlap; that check includes row padding. Stats are optional and must be
 * outside input/workspace. Stats are initialized only after argument/workspace
 * validation succeeds. The supplied workspace may be reused after return.
 */
png16_result png16_encode(
    const uint8_t *input_le16, size_t input_bytes,
    uint32_t width, uint32_t height, size_t stride_bytes,
    png16_mode mode, void *workspace, size_t workspace_bytes,
    png16_write_fn write, void *user, png16_stats *stats);

/* As above, with optional profiling. NULL timing is identical to the original
 * API. Otherwise now/out are required and the config/output must not overlap
 * input, workspace, stats or each other. The output is initialized only after
 * argument validation. Timer callbacks run at row/call/chunk boundaries,
 * never per pixel or compressed byte. No hardware clock is accessed directly.
 * total_cycles starts after validation and ends before final stats/timing
 * publication, so the enclosing caller timer is necessarily slightly longer.
 */
png16_result png16_encode_timed(
    const uint8_t *input_le16, size_t input_bytes,
    uint32_t width, uint32_t height, size_t stride_bytes,
    png16_mode mode, void *workspace, size_t workspace_bytes,
    png16_write_fn write, void *user, png16_stats *stats,
    const png16_timing_config *timing);

#ifdef __cplusplus
}
#endif
#endif
