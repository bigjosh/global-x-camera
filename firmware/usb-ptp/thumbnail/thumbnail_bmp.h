#ifndef GX_THUMBNAIL_BMP_H
#define GX_THUMBNAIL_BMP_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define GX_THUMB_WIDTH 128u
#define GX_THUMB_HEIGHT 156u
#define GX_THUMB_FORMAT 0x3804u /* PTP BMP, pending actual host qualification. */
#define GX_THUMB_SIZE (54u + GX_THUMB_WIDTH * 3u * GX_THUMB_HEIGHT)
#define GX_THUMB_RAW_WIDTH 1120u
#define GX_THUMB_RAW_HEIGHT 1364u
#define GX_THUMB_RAW_BYTES (GX_THUMB_RAW_WIDTH * GX_THUMB_RAW_HEIGHT * 5u / 4u)

/* Render any slice of one 24-bit BMP from a fully read RAW10 RAM snapshot.
 * No allocation, SD access, caching, gamma transform or changes to the source.
 * RAW10 begins at the first pixel, not at the slot's magic/metadata prefix.
 * Returns 0, setting written (possibly short at EOF), or -1 for invalid input.
 * Caller must keep raw unchanged for the complete PTP transaction. This
 * preview intentionally reduces precision; the PNG16 object remains exact.
 */
int gx_thumbnail_bmp_read(const uint8_t *raw, size_t raw_size,
                          uint32_t offset, uint8_t *dst, size_t requested,
                          size_t *written);
#ifdef __cplusplus
}
#endif
#endif
