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
    PNG16_FAST_SUB = 2
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

#ifdef __cplusplus
}
#endif
#endif
