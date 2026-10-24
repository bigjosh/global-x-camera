#include "png16.h"
#include "miniz_config.h"
#include "vendor/miniz/miniz.h"

typedef struct {
    tdefl_compressor compressor;
    /* Stored mode prepends a five-byte DEFLATE block header in this same row
     * buffer. Fast modes still render at offset zero and use miniz unchanged. */
    uint8_t row[5U + 1U + 2U * PNG16_MAX_WIDTH];
    png16_write_fn write;
    void *user;
    png16_stats stats;
    png16_result error;
    png16_timing_config clock;
    png16_timing timing;
    uint64_t clock_last;
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

static uint64_t tick(encoder *e)
{
    if (!e->clock.now) return 0;
    uint64_t now=e->clock.now(e->clock.user);
    if (e->timing.clock_calls && now<e->clock_last) e->timing.clock_error|=1U;
    ++e->timing.clock_calls;
    e->clock_last=now;
    return now;
}

static void accumulate(encoder *e, uint64_t *sum, uint64_t start)
{
    if (!e->clock.now) return;
    uint64_t end=tick(e);
    if (end<start || end-start>UINT64_MAX-*sum) {
        e->timing.clock_error|=2U;
        return;
    }
    *sum+=end-start;
}

static uint64_t subtract(encoder *e, uint64_t whole, uint64_t part)
{
    if (part>whole) { e->timing.clock_error|=2U; return 0; }
    return whole-part;
}

static int emit(encoder *e, const uint8_t *data, size_t n)
{
    if (e->error != PNG16_OK) return 0;
    while (n) {
        size_t part=n>PNG16_MAX_CALLBACK_BYTES ? PNG16_MAX_CALLBACK_BYTES : n;
        ++e->stats.callback_calls;
        uint64_t start=tick(e);
        int accepted=e->write(e->user,data,part);
        accumulate(e,&e->timing.callback_cycles,start);
        if (!accepted) {
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
    uint64_t start=tick(e), callback_before=e->timing.callback_cycles;
    uint8_t header[8], trailer[4];
    be32(header,n);
    for (unsigned i=0;i<4;++i) header[4+i]=(uint8_t)type[i];
    uint32_t crc=(uint32_t)mz_crc32(0,header+4,4);
    if (n) crc=(uint32_t)mz_crc32(crc,data,n);
    be32(trailer,crc);
    int result=emit(e,header,sizeof(header)) &&
               (!n || emit(e,data,n)) && emit(e,trailer,sizeof(trailer));
    accumulate(e,&e->timing.framing_inclusive_cycles,start);
    /* Chunk calls cannot nest; the signature's callback is outside chunks. */
    e->timing.framing_callback_cycles+=e->timing.callback_cycles-callback_before;
    return result;
}

static mz_bool compressed_output(const void *data, int length, void *user)
{
    encoder *e=(encoder *)user;
    uint64_t start=tick(e);
    const uint8_t *p=(const uint8_t *)data;
    mz_bool result=MZ_TRUE;
    if (length<0) { e->error=PNG16_COMPRESS_FAILED; result=MZ_FALSE; goto done; }
    while (length) {
        uint32_t n=(uint32_t)length;
        if (n>PNG16_MAX_CALLBACK_BYTES) n=PNG16_MAX_CALLBACK_BYTES;
        if (!chunk(e,"IDAT",p,n)) { result=MZ_FALSE; goto done; }
        ++e->stats.idat_chunks;
        p+=n; length-=(int)n;
    }
done:
    accumulate(e,&e->timing.deflate_output_cycles,start);
    return result;
}

static int overlap(const void *a, size_t an, const void *b, size_t bn)
{
    uintptr_t aa=(uintptr_t)a, bb=(uintptr_t)b;
    /* Validated extents cannot wrap the address space. */
    return aa < bb+bn && bb < aa+an;
}

png16_result png16_encode_timed(
    const uint8_t *input, size_t input_bytes,
    uint32_t width, uint32_t height, size_t stride,
    png16_mode mode, void *workspace, size_t workspace_bytes,
    png16_write_fn write, void *user, png16_stats *stats,
    const png16_timing_config *timing)
{
    const size_t row_bytes=(size_t)width*2U;
    size_t extent;
    if (!input || !workspace || !write || !width || !height ||
        width>PNG16_MAX_WIDTH || height>PNG16_MAX_HEIGHT ||
        stride<row_bytes || (unsigned)mode>PNG16_HUFFMAN_SUB ||
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
    if (timing) {
        if (sizeof(*timing)>UINTPTR_MAX-(uintptr_t)timing ||
            overlap(timing,sizeof(*timing),input,extent) ||
            overlap(timing,sizeof(*timing),workspace,sizeof(encoder)) ||
            (stats && overlap(timing,sizeof(*timing),stats,sizeof(*stats))))
            return PNG16_BAD_ARGUMENT;
        if (!timing->now || !timing->out ||
            sizeof(*timing->out)>UINTPTR_MAX-(uintptr_t)timing->out ||
            overlap(timing->out,sizeof(*timing->out),input,extent) ||
            overlap(timing->out,sizeof(*timing->out),workspace,sizeof(encoder)) ||
            overlap(timing->out,sizeof(*timing->out),timing,sizeof(*timing)) ||
            (stats && overlap(timing->out,sizeof(*timing->out),stats,sizeof(*stats))))
            return PNG16_BAD_ARGUMENT;
    }
    encoder *e=(encoder *)workspace;
    e->write=write; e->user=user; e->error=PNG16_OK;
    e->stats=(png16_stats){0};
    e->clock=timing ? *timing : (png16_timing_config){0};
    e->timing=(png16_timing){0}; e->clock_last=0;
    if (stats) *stats=e->stats;
    if (e->clock.out) *e->clock.out=e->timing;
    uint64_t total_start=tick(e);

    const int stored=mode==PNG16_STORED_NONE;
    uint32_t adler=1;
    if (!stored) {
        const int flags=mode==PNG16_HUFFMAN_SUB ?
            TDEFL_WRITE_ZLIB_HEADER | TDEFL_FAST_HUFFMAN_ONLY :
            TDEFL_WRITE_ZLIB_HEADER | TDEFL_GREEDY_PARSING_FLAG | 1;
        uint64_t start=tick(e);
        tdefl_status status=tdefl_init(&e->compressor,compressed_output,e,flags);
        accumulate(e,&e->timing.deflate_inclusive_cycles,start);
        if (status!=TDEFL_STATUS_OKAY) { e->error=PNG16_COMPRESS_FAILED; goto done; }
    }
    static const uint8_t signature[8]={137,80,78,71,13,10,26,10};
    uint8_t ihdr[13]={0}, significant=10;
    be32(ihdr,width); be32(ihdr+4,height);
    ihdr[8]=16; /* Color0, deflate0, filter0, interlace0 already zero. */
    if (!emit(e,signature,sizeof(signature)) ||
        !chunk(e,"IHDR",ihdr,sizeof(ihdr)) ||
        !chunk(e,"sBIT",&significant,1))
        goto done;
    if (stored) {
        /* RFC 1950: DEFLATE, 32 KiB window, no dictionary, fastest level.
         * 0x7801 is a multiple of 31. All following blocks are byte-aligned. */
        static const uint8_t zlib_header[2]={0x78,0x01};
        if (!chunk(e,"IDAT",zlib_header,sizeof(zlib_header))) goto done;
        ++e->stats.idat_chunks;
    }
    for (uint32_t y=0;y<height;++y) {
        uint64_t conversion_start=tick(e);
        const uint8_t *p=input+(size_t)y*stride;
        uint8_t *row=e->row+(stored ? 5U : 0U);
        uint8_t prev_hi=0,prev_lo=0;
        const int sub=mode==PNG16_FAST_SUB || mode==PNG16_HUFFMAN_SUB;
        row[0]=sub ? 1U : 0U;
        for (uint32_t x=0;x<width;++x) {
            uint32_t v=(uint32_t)p[2*x]|((uint32_t)p[2*x+1]<<8);
            if (v>1023U) {
                e->error=PNG16_BAD_SAMPLE;
                accumulate(e,&e->timing.conversion_cycles,conversion_start);
                goto done;
            }
            uint8_t hi=(uint8_t)(v>>2),lo=(uint8_t)(v<<6);
            row[2*x+1]=sub ? (uint8_t)(hi-prev_hi) : hi;
            row[2*x+2]=sub ? (uint8_t)(lo-prev_lo) : lo;
            prev_hi=hi; prev_lo=lo;
        }
        accumulate(e,&e->timing.conversion_cycles,conversion_start);
        uint64_t deflate_start=tick(e);
        if (stored) {
            /* RFC 1951 stored block: BFINAL/BTYPE=00 + zero alignment bits,
             * then little-endian LEN/NLEN. Maximum row is only 2241 bytes.
             * Direct emission avoids miniz's per-byte LZ/hash/literal path. */
            uint32_t n=(uint32_t)row_bytes+1U, complement=n^0xFFFFU;
            e->row[0]=(uint8_t)(y+1U==height);
            e->row[1]=(uint8_t)n; e->row[2]=(uint8_t)(n>>8);
            e->row[3]=(uint8_t)complement; e->row[4]=(uint8_t)(complement>>8);
            adler=(uint32_t)mz_adler32(adler,row,n);
            accumulate(e,&e->timing.deflate_inclusive_cycles,deflate_start);
            if (!chunk(e,"IDAT",e->row,n+5U)) goto done;
            ++e->stats.idat_chunks;
        } else {
            tdefl_status status=tdefl_compress_buffer(&e->compressor,row,row_bytes+1,
                                                     TDEFL_NO_FLUSH);
            accumulate(e,&e->timing.deflate_inclusive_cycles,deflate_start);
            if (status!=TDEFL_STATUS_OKAY) {
                if (e->error==PNG16_OK) e->error=PNG16_COMPRESS_FAILED;
                goto done;
            }
        }
        ++e->stats.rows_encoded;
    }
    if (stored) {
        uint8_t footer[4];
        be32(footer,adler);
        if (!chunk(e,"IDAT",footer,sizeof(footer))) goto done;
        ++e->stats.idat_chunks;
    } else {
        uint64_t start=tick(e);
        tdefl_status status=tdefl_compress_buffer(&e->compressor,NULL,0,TDEFL_FINISH);
        accumulate(e,&e->timing.deflate_inclusive_cycles,start);
        if (status!=TDEFL_STATUS_DONE) {
            if (e->error==PNG16_OK) e->error=PNG16_COMPRESS_FAILED;
            goto done;
        }
    }
    (void)chunk(e,"IEND",NULL,0);
done:
    accumulate(e,&e->timing.total_cycles,total_start);
    e->timing.deflate_cycles=subtract(e,e->timing.deflate_inclusive_cycles,
                                       e->timing.deflate_output_cycles);
    e->timing.framing_cycles=subtract(e,e->timing.framing_inclusive_cycles,
                                       e->timing.framing_callback_cycles);
    uint64_t other=e->timing.total_cycles;
    other=subtract(e,other,e->timing.conversion_cycles);
    other=subtract(e,other,e->timing.deflate_cycles);
    other=subtract(e,other,e->timing.framing_cycles);
    other=subtract(e,other,e->timing.callback_cycles);
    e->timing.other_cycles=other;
    if (stats) *stats=e->stats;
    if (e->clock.out) *e->clock.out=e->timing;
    return e->error;
}

png16_result png16_encode(
    const uint8_t *input, size_t input_bytes,
    uint32_t width, uint32_t height, size_t stride,
    png16_mode mode, void *workspace, size_t workspace_bytes,
    png16_write_fn write, void *user, png16_stats *stats)
{
    return png16_encode_timed(input,input_bytes,width,height,stride,mode,
        workspace,workspace_bytes,write,user,stats,NULL);
}
