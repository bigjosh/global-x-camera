#include "png16.h"
#include "miniz_config.h"
#include "vendor/miniz/miniz.h"

typedef struct {
    tdefl_compressor compressor;
    uint8_t row[1U + 2U * PNG16_MAX_WIDTH];
    png16_write_fn write;
    void *user;
    png16_stats stats;
    png16_result error;
} encoder;

_Static_assert(sizeof(encoder) <= PNG16_WORKSPACE_BYTES, "PNG workspace budget");
_Static_assert(_Alignof(encoder) <= _Alignof(png16_workspace), "PNG alignment");

size_t png16_workspace_size(void) { return sizeof(encoder); }
size_t png16_workspace_alignment(void) { return _Alignof(encoder); }

static void be32(uint8_t *p, uint32_t v)
{
    p[0]=(uint8_t)(v>>24); p[1]=(uint8_t)(v>>16);
    p[2]=(uint8_t)(v>>8); p[3]=(uint8_t)v;
}

static int emit(encoder *e, const uint8_t *data, size_t n)
{
    if (e->error != PNG16_OK) return 0;
    while (n) {
        size_t part=n>PNG16_MAX_CALLBACK_BYTES ? PNG16_MAX_CALLBACK_BYTES : n;
        ++e->stats.callback_calls;
        if (!e->write(e->user,data,part)) {
            e->error=PNG16_WRITE_FAILED;
            return 0;
        }
        e->stats.output_bytes+=part;
        data+=part; n-=part;
    }
    return 1;
}

static int chunk(encoder *e, const char type[4], const uint8_t *data, uint32_t n)
{
    uint8_t header[8], trailer[4];
    be32(header,n);
    for (unsigned i=0;i<4;++i) header[4+i]=(uint8_t)type[i];
    uint32_t crc=(uint32_t)mz_crc32(0,header+4,4);
    if (n) crc=(uint32_t)mz_crc32(crc,data,n);
    be32(trailer,crc);
    return emit(e,header,sizeof(header)) &&
           (!n || emit(e,data,n)) && emit(e,trailer,sizeof(trailer));
}

static mz_bool compressed_output(const void *data, int length, void *user)
{
    encoder *e=(encoder *)user;
    const uint8_t *p=(const uint8_t *)data;
    if (length<0) { e->error=PNG16_COMPRESS_FAILED; return MZ_FALSE; }
    while (length) {
        uint32_t n=(uint32_t)length;
        if (n>PNG16_MAX_CALLBACK_BYTES) n=PNG16_MAX_CALLBACK_BYTES;
        if (!chunk(e,"IDAT",p,n)) return MZ_FALSE;
        ++e->stats.idat_chunks;
        p+=n; length-=(int)n;
    }
    return MZ_TRUE;
}

static int overlap(const void *a, size_t an, const void *b, size_t bn)
{
    uintptr_t aa=(uintptr_t)a, bb=(uintptr_t)b;
    /* Validated extents cannot wrap the address space. */
    return aa < bb+bn && bb < aa+an;
}

png16_result png16_encode(
    const uint8_t *input, size_t input_bytes,
    uint32_t width, uint32_t height, size_t stride,
    png16_mode mode, void *workspace, size_t workspace_bytes,
    png16_write_fn write, void *user, png16_stats *stats)
{
    const size_t row_bytes=(size_t)width*2U;
    size_t extent;
    if (!input || !workspace || !write || !width || !height ||
        width>PNG16_MAX_WIDTH || height>PNG16_MAX_HEIGHT ||
        stride<row_bytes || (unsigned)mode>PNG16_FAST_SUB ||
        (height>1U && stride>(SIZE_MAX-row_bytes)/(height-1U)))
        return PNG16_BAD_ARGUMENT;
    extent=(size_t)(height-1U)*stride+row_bytes;
    if (input_bytes<extent || extent>UINTPTR_MAX-(uintptr_t)input)
        return PNG16_BAD_ARGUMENT;
    if (workspace_bytes<sizeof(encoder) ||
        (uintptr_t)workspace % _Alignof(encoder) ||
        sizeof(encoder)>UINTPTR_MAX-(uintptr_t)workspace ||
        overlap(input,extent,workspace,sizeof(encoder)))
        return PNG16_BAD_WORKSPACE;
    if (stats && (sizeof(*stats)>UINTPTR_MAX-(uintptr_t)stats ||
                  overlap(stats,sizeof(*stats),input,extent) ||
                  overlap(stats,sizeof(*stats),workspace,sizeof(encoder))))
        return PNG16_BAD_ARGUMENT;
    encoder *e=(encoder *)workspace;
    e->write=write; e->user=user; e->error=PNG16_OK;
    e->stats=(png16_stats){0};
    if (stats) *stats=e->stats;

    int flags=TDEFL_WRITE_ZLIB_HEADER | TDEFL_GREEDY_PARSING_FLAG;
    flags|=mode==PNG16_STORED_NONE ? TDEFL_FORCE_ALL_RAW_BLOCKS : 1;
    if (tdefl_init(&e->compressor,compressed_output,e,flags)!=TDEFL_STATUS_OKAY)
        return PNG16_COMPRESS_FAILED;
    static const uint8_t signature[8]={137,80,78,71,13,10,26,10};
    uint8_t ihdr[13]={0}, significant=10;
    be32(ihdr,width); be32(ihdr+4,height);
    ihdr[8]=16; /* Color0, deflate0, filter0, interlace0 already zero. */
    if (!emit(e,signature,sizeof(signature)) ||
        !chunk(e,"IHDR",ihdr,sizeof(ihdr)) ||
        !chunk(e,"sBIT",&significant,1))
        goto done;
    for (uint32_t y=0;y<height;++y) {
        const uint8_t *p=input+(size_t)y*stride;
        uint8_t prev_hi=0,prev_lo=0;
        e->row[0]=mode==PNG16_FAST_SUB ? 1U : 0U;
        for (uint32_t x=0;x<width;++x) {
            uint32_t v=(uint32_t)p[2*x]|((uint32_t)p[2*x+1]<<8);
            if (v>1023U) { e->error=PNG16_BAD_SAMPLE; goto done; }
            uint8_t hi=(uint8_t)(v>>2),lo=(uint8_t)(v<<6);
            e->row[2*x+1]=mode==PNG16_FAST_SUB ? (uint8_t)(hi-prev_hi) : hi;
            e->row[2*x+2]=mode==PNG16_FAST_SUB ? (uint8_t)(lo-prev_lo) : lo;
            prev_hi=hi; prev_lo=lo;
        }
        if (tdefl_compress_buffer(&e->compressor,e->row,row_bytes+1,
                                 TDEFL_NO_FLUSH)!=TDEFL_STATUS_OKAY) {
            if (e->error==PNG16_OK) e->error=PNG16_COMPRESS_FAILED;
            goto done;
        }
        ++e->stats.rows_encoded;
    }
    if (tdefl_compress_buffer(&e->compressor,NULL,0,TDEFL_FINISH)!=TDEFL_STATUS_DONE) {
        if (e->error==PNG16_OK) e->error=PNG16_COMPRESS_FAILED;
        goto done;
    }
    (void)chunk(e,"IEND",NULL,0);
done:
    if (stats) *stats=e->stats;
    return e->error;
}
