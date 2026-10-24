/* Isolated profiling only; no per-byte probes, no DWT resets.
 * Each coarse interval is below one 32-bit CYCCNT wrap. Accumulators are64-bit.
 * Nested counters deliberately overlap; use the documented subtraction map.
 * Host clock is for output-equivalence tests, not MCU timing claims. */
#if !defined(__arm__) && !defined(__thumb__)
#include <time.h>
#endif
#define MP_N 14
static mz_uint64 mp_cycles[MP_N];
static mz_uint32 mp_calls[MP_N],mp_clock_reads;
static mz_uint32 mp_now(void) {
    ++mp_clock_reads;
#if defined(__arm__) || defined(__thumb__)
    return *(volatile mz_uint32 *)0xE0001004U;
#else
    return (mz_uint32)clock();
#endif
}
static void mp_add(unsigned id,mz_uint32 start) {
    mz_uint32 elapsed=mp_now()-start;
    mp_cycles[id]+=elapsed; ++mp_calls[id];
}
void png16_miniz_profile_reset(void) {
    memset(mp_cycles,0,sizeof(mp_cycles));memset(mp_calls,0,sizeof(mp_calls));
    mp_clock_reads=0;
}
void png16_miniz_profile_export(volatile mz_uint32 *words) {
    unsigned i;
    for(i=0;i<53;i++) words[i]=0;
    words[0]=0x4d504631U;words[1]=1;words[2]=MP_N;words[3]=mp_clock_reads;
    for(i=0;i<MP_N;i++) {
        words[4+i*2]=(mz_uint32)mp_cycles[i];
        words[5+i*2]=(mz_uint32)(mp_cycles[i]>>32);
        words[32+i]=mp_calls[i];
    }
#if defined(__arm__) || defined(__thumb__)
    words[46]=1; /* DWT nominal CPU-cycle clock; no reset/write */
#else
    words[46]=0; /* C runtime clock ticks; correctness tests only */
#endif
    words[47]=53;
}
static mz_ulong mp_adler(mz_ulong adler,const unsigned char *p,size_t n) {
    mz_uint32 t=mp_now();mz_ulong result=mz_adler32(adler,p,n);mp_add(7,t);return result;
}
static mz_bool mp_output(tdefl_compressor *d,int n) {
    mz_uint32 t=mp_now();
    mz_bool result=(*d->m_pPut_buf_func)(d->m_output_buf,n,d->m_pPut_buf_user);
    mp_add(8,t);return result;
}
