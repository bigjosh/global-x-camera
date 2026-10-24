#ifndef PNG_ROW_CONVERT_H
#define PNG_ROW_CONVERT_H
#include <stdint.h>
/* One row, source LE16 right-aligned RAW10, output PNG filter byte + BE16
 * samples left-shifted six. src[2*width] and row[1+2*width] must be disjoint.
 * Byte alignment is sufficient. sub is exactly 0 or 1. Return 1 on valid
 * samples, 0 on an invalid sample/mode. On failure output is unspecified and
 * MUST NOT be compressed/emitted. No state, allocation or peripheral access. */
int png16_row_reference(const uint8_t *, uint8_t *, uint32_t, int);
int png16_row_scalar(const uint8_t *, uint8_t *, uint32_t, int);
int png16_row_mve(const uint8_t *, uint8_t *, uint32_t, int);
#endif
