#include "thumbnail_bmp.h"

static void le16(uint8_t *p, uint16_t v) {
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
}
static void le32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

int gx_thumbnail_bmp_read(const uint8_t *raw, size_t raw_size,
                          uint32_t offset, uint8_t *dst, size_t requested,
                          size_t *written) {
    uint8_t header[54] = {0};
    size_t n, i;
    if (!written) return -1;
    *written = 0;
    if (!raw || raw_size < GX_THUMB_RAW_BYTES || (!dst && requested) || offset > GX_THUMB_SIZE) return -1;
    n = GX_THUMB_SIZE - offset;
    if (n > requested) n = requested;
    header[0] = 'B'; header[1] = 'M';
    le32(header + 2, GX_THUMB_SIZE);
    le32(header + 10, sizeof(header));
    le32(header + 14, 40); /* BITMAPINFOHEADER */
    le32(header + 18, GX_THUMB_WIDTH);
    le32(header + 22, GX_THUMB_HEIGHT); /* positive: BMP bottom-up rows */
    le16(header + 26, 1); le16(header + 28, 24);
    le32(header + 34, GX_THUMB_SIZE - sizeof(header));
    for (i = 0; i < n; ++i) {
        uint32_t pos = offset + (uint32_t)i;
        if (pos < sizeof(header)) {
            dst[i] = header[pos];
        } else {
            uint32_t p = (pos - sizeof(header)) / 3u;
            uint32_t x = p % GX_THUMB_WIDTH;
            uint32_t y = GX_THUMB_HEIGHT - 1u - p / GX_THUMB_WIDTH;
            uint32_t sx = ((2u * x + 1u) * GX_THUMB_RAW_WIDTH) / (2u * GX_THUMB_WIDTH);
            uint32_t sy = ((2u * y + 1u) * GX_THUMB_RAW_HEIGHT) / (2u * GX_THUMB_HEIGHT);
            /* First four bytes of each five-byte MIPI group are bits9:2.
             * All B/G/R channels receive the same high eight sensor bits. */
            uint32_t source = sy * (GX_THUMB_RAW_WIDTH * 5u / 4u) + (sx / 4u) * 5u + sx % 4u;
            dst[i] = raw[source];
        }
    }
    *written = n;
    return 0;
}
