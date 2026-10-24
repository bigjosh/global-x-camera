#include "row_convert.h"
#if defined(PNG16_TEST_MVE_MODEL)
#include "mve_model.h"
#define ROW_HAS_MVE 1
#elif defined(__ARM_FEATURE_MVE) && (__ARM_FEATURE_MVE & 1)
#include <arm_mve.h>
#define ROW_HAS_MVE 1
#else
#define ROW_HAS_MVE 0
#endif

static uint32_t sample(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8);
}

int png16_row_reference(const uint8_t *src, uint8_t *row,
                        uint32_t width, int sub) {
    if (sub != 0 && sub != 1) return 0;
    uint8_t ph=0, pl=0;
    row[0]=(uint8_t)sub;
    for (uint32_t i=0;i<width;++i) {
        uint32_t v=sample(src+2*i);
        if (v>1023) return 0;
        uint8_t h=(uint8_t)(v>>2), l=(uint8_t)(v<<6);
        row[2*i+1]=sub ? (uint8_t)(h-ph) : h;
        row[2*i+2]=sub ? (uint8_t)(l-pl) : l;
        ph=h; pl=l;
    }
    return 1;
}

int png16_row_scalar(const uint8_t *src, uint8_t *row,
                     uint32_t width, int sub) {
    if (sub != 0 && sub != 1) return 0;
    uint32_t all=0;
    row[0]=(uint8_t)sub;
    if (sub) {
        uint8_t ph=0, pl=0;
        for (uint32_t i=0;i<width;++i) {
            uint32_t v=sample(src+2*i); all|=v;
            uint8_t h=(uint8_t)(v>>2), l=(uint8_t)(v<<6);
            row[2*i+1]=(uint8_t)(h-ph);
            row[2*i+2]=(uint8_t)(l-pl);
            ph=h; pl=l;
        }
    } else {
        for (uint32_t i=0;i<width;++i) {
            uint32_t v=sample(src+2*i); all|=v;
            row[2*i+1]=(uint8_t)(v>>2);
            row[2*i+2]=(uint8_t)(v<<6);
        }
    }
    return !(all & 0xfc00U);
}

int png16_row_mve(const uint8_t *src, uint8_t *row,
                  uint32_t width, int sub) {
#if ROW_HAS_MVE
    if (sub != 0 && sub != 1) return 0;
    uint32_t i=0, all=0;
    uint16x8_t combined=vdupq_n_u16(0);
    row[0]=(uint8_t)sub;
    if (sub && width) {
        /* First pixel has an all-zero predecessor; then both overlapping
         * vector loads are fully inside the caller's exact source row. */
        uint32_t v=sample(src); all|=v;
        row[1]=(uint8_t)(v>>2); row[2]=(uint8_t)(v<<6); i=1;
    }
    if (sub) {
        for (;width-i>=8;i+=8) {
            uint16x8_t v=vreinterpretq_u16_u8(vld1q_u8(src+2*i));
            uint16x8_t p=vreinterpretq_u16_u8(vld1q_u8(src+2*(i-1)));
            combined=vorrq_u16(combined,v);
            uint8x16_t b=vrev16q_u8(vreinterpretq_u8_u16(vshlq_n_u16(v,6)));
            uint8x16_t prev=vrev16q_u8(vreinterpretq_u8_u16(vshlq_n_u16(p,6)));
            vst1q_u8(row+1+2*i,vsubq_u8(b,prev));
        }
    } else {
        for (;width-i>=8;i+=8) {
            /* Byte loads/stores preserve the public odd-address contract;
             * no uint16_t pointer cast, alignment assumption or overread. */
            uint16x8_t v=vreinterpretq_u16_u8(vld1q_u8(src+2*i));
            combined=vorrq_u16(combined,v);
            vst1q_u8(row+1+2*i,
                vrev16q_u8(vreinterpretq_u8_u16(vshlq_n_u16(v,6))));
        }
    }
    all|=vmaxvq_u16(0,combined);
    for (;i<width;++i) {
        uint32_t v=sample(src+2*i); all|=v;
        uint32_t p=(sub && i) ? sample(src+2*(i-1)) : 0;
        row[2*i+1]=(uint8_t)((uint8_t)(v>>2)-(uint8_t)(p>>2));
        row[2*i+2]=(uint8_t)((uint8_t)(v<<6)-(uint8_t)(p<<6));
    }
    /* A lane contains a forbidden upper bit iff its value exceeds 1023;
     * OR accumulation preserves that fact across chunks and lanes. */
    return !(all & 0xfc00U);
#else
    return png16_row_scalar(src,row,width,sub);
#endif
}
