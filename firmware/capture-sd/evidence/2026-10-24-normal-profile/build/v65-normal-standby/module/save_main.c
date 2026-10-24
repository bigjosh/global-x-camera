/* Post-capture storage module and explicit, guarded RAM bench operations. */
#include <string.h>
#include "stm32n6xx.h"
#include "status_leds.h"
#include "save_protocol.h"
#include "photo_fs.h"
#include "png16.h"
#include "phase_gpio.h"

#ifndef SAVE_DATA_CACHE
#define SAVE_DATA_CACHE 0
#endif
static sd_card_t card;
/* Encoding and host READ never run together. Keep SAVE buffering identical
 * while making guarded readback practical without another 256 KiB allocation. */
static union {
    png16_workspace png;
    uint8_t read[SAVE_READ_BUFFER_BYTES];
} scratch __attribute__((aligned(32)));
static uint8_t output_buffer[SAVE_BUFFER_BYTES] __attribute__((aligned(32)));
static uint32_t buffered, last_cycle, frame_checked;
static uint64_t elapsed, callback_cycles;
static volatile uint32_t *const report=(volatile uint32_t *)SAVE_REPORT_ADDRESS;

static uint64_t clock_now(void)
{
    uint32_t now=DWT->CYCCNT;
    elapsed+=(uint32_t)(now-last_cycle);
    last_cycle=now;
    return elapsed;
}
static uint64_t png_clock(void *unused) { (void)unused; return clock_now(); }
/* sd_card.c calls between commands and while waiting; keeps CYCCNT extended
 * even when formatting/scanning the filesystem takes longer than one wrap. */
void sd_progress(void) { (void)clock_now(); }
static void pair(unsigned field, uint64_t value)
{
    report[field]=(uint32_t)value; report[field+1]=(uint32_t)(value>>32);
}
static void snapshot(void)
{
    const photo_fs_report_t *fs=photo_fs_get_report();
    memcpy((void *)SAVE_CARD_ADDRESS,&card,sizeof(card));
    memcpy((void *)SAVE_FS_ADDRESS,fs,sizeof(*fs));
    report[P_CARD_ERROR]=card.error;
    report[P_FS_RESULT]=fs->fat_result; report[P_FS_STAGE]=fs->stage;
    report[P_MEDIA_IDLE]=card.media_idle;
    if(fs->final_name[0]) memcpy((void *)(report+P_NAME),fs->final_name,13);
    __DSB();
}
static int flush_buffer(void)
{
    if(!buffered) return 0;
    int result=photo_fs_append(output_buffer,buffered);
    report[P_BUFFER_FLUSHES]++;
    if(!result) buffered=0;
    return result;
}
static int append_png(void *unused, const uint8_t *data, size_t bytes)
{
    (void)unused;
    uint64_t start=clock_now();
    int result=0;
    while(bytes) {
        size_t n=sizeof(output_buffer)-buffered;
        if(n>bytes) n=bytes;
        memcpy(output_buffer+buffered,data,n);
        buffered+=(uint32_t)n; data+=n; bytes-=n;
        if(buffered==sizeof(output_buffer) && (result=flush_buffer())) break;
    }
    callback_cycles+=clock_now()-start;
    return result==0;
}
#if CAPTURE_DIAGNOSTICS
static uint32_t frame_fnv(void)
{
    const uint8_t *p=(const uint8_t *)SAVE_FRAME_ADDRESS;
    uint32_t value=2166136261U;
    for(unsigned i=0;i<SAVE_FRAME_BYTES;i++) value=(value^p[i])*16777619U;
    return value;
}
#endif
static int frame_valid(void)
{
    const volatile uint32_t *trace=(void *)0x343F0000U;
    const volatile uint32_t *raw=(void *)0x343F6000U;
    const volatile uint32_t *guard=(void *)(SAVE_FRAME_ADDRESS+SAVE_FRAME_BYTES);
    const volatile uint32_t *profile=(void *)CAPTURE_PROFILE_ADDRESS;
    if(profile[CP_MAGIC]!=CAPTURE_PROFILE_MAGIC || profile[CP_SCHEMA]!=2U ||
       profile[CP_WORDS]!=32U || profile[CP_PROFILE]!=CAPTURE_DIAGNOSTICS ||
       profile[CP_STATE]!=2U ||
       profile[CP_FLAGS]!=(CAPTURE_DIAGNOSTICS ? 0x7FU : 0x1FU) ||
       profile[CP_FRAME]!=SAVE_FRAME_ADDRESS || profile[CP_BYTES]!=SAVE_FRAME_BYTES ||
       profile[CP_WIDTH]!=SAVE_WIDTH || profile[CP_HEIGHT]!=SAVE_HEIGHT ||
       profile[CP_BITS]!=10U || profile[CP_DATA_TYPE]!=0x2BU ||
       profile[CP_DMA_BYTES]!=SAVE_FRAME_BYTES || profile[CP_ERRORS] ||
       profile[CP_CANARY_MASK]!=255U) return 0;
    if(CAPTURE_DIAGNOSTICS ? profile[CP_FNV]!=trace[11] :
       (profile[CP_FNV] || trace[8] || trace[9] || trace[10] || trace[11])) return 0;
    if(trace[0]!=0x43545031U || trace[1]!=40U ||
       trace[4] || trace[5]!=1U || trace[7] ||
       trace[12]!=SAVE_FRAME_ADDRESS || trace[13]!=SAVE_FRAME_BYTES ||
       trace[14]!=SAVE_WIDTH || trace[15]!=SAVE_HEIGHT ||
       raw[0]!=0x52313046U || raw[1]!=SAVE_FRAME_BYTES || raw[7] ||
       raw[8]!=10U || raw[9]!=0x2BU) return 0;
    for(unsigned i=0;i<8;i++) if(guard[i]!=0xA15A1000U+i) return 0;
    return 1;
}
static int save_image(png16_mode mode)
{
    uint64_t start=clock_now();
    report[P_STAGE]=2;
    report[P_CHECKS_PERFORMED]|=SAVE_CHECK_FRAME;
    if(!frame_valid()) return -201;
#if CAPTURE_DIAGNOSTICS
    report[P_CHECKS_PERFORMED]|=SAVE_CHECK_PREHASH;
    report[P_FNV_BEFORE]=frame_fnv();
    if(report[P_FNV_BEFORE]!=((volatile uint32_t *)0x343F0000U)[11]) return -202;
#endif
    frame_checked=1;
    pair(P_VALIDATE_LO,clock_now()-start);
    report[P_STAGE]=4;
    start=clock_now();
    int result=photo_fs_open(SAVE_MAX_PNG_BYTES);
    pair(P_OPEN_LO,clock_now()-start);
    if(result) return result;
    snapshot();
    report[P_STAGE]=5;
    png16_stats stats={0};
    png16_timing timing={0};
    const png16_timing_config timing_config={png_clock,0,&timing};
    start=clock_now();
    report[P_CHECKS_PERFORMED]|=SAVE_CHECK_PNG_TIMING;
    int png_result=png16_encode_timed((const void *)SAVE_FRAME_ADDRESS,SAVE_FRAME_BYTES,
        SAVE_WIDTH,SAVE_HEIGHT,SAVE_WIDTH*2U,mode,scratch.png.bytes,sizeof(scratch.png),
        append_png,0,&stats,&timing_config);
    pair(P_ENCODE_LO,clock_now()-start);
    pair(P_PNG_TOTAL_LO,timing.total_cycles);
    pair(P_PNG_CONVERSION_LO,timing.conversion_cycles);
    pair(P_PNG_DEFLATE_LO,timing.deflate_cycles);
    pair(P_PNG_FRAMING_LO,timing.framing_cycles);
    pair(P_PNG_CALLBACK_LO,timing.callback_cycles);
    pair(P_PNG_OTHER_LO,timing.other_cycles);
    pair(P_PNG_DEFLATE_INCLUSIVE_LO,timing.deflate_inclusive_cycles);
    pair(P_PNG_DEFLATE_OUTPUT_LO,timing.deflate_output_cycles);
    pair(P_PNG_FRAMING_INCLUSIVE_LO,timing.framing_inclusive_cycles);
    pair(P_PNG_FRAMING_CALLBACK_LO,timing.framing_callback_cycles);
    report[P_PNG_CLOCK_CALLS]=timing.clock_calls;
    report[P_PNG_CLOCK_ERROR]=timing.clock_error;
    pair(P_CALLBACK_LO,callback_cycles);
    pair(P_PNG_BYTES_LO,stats.output_bytes);
    report[P_ROWS]=stats.rows_encoded; report[P_IDAT_CHUNKS]=stats.idat_chunks;
    report[P_CALLBACKS]=stats.callback_calls; report[P_PNG_RESULT]=(uint32_t)png_result;
    if(png_result) return png_result;
    (void)phase_gpio_emit(7U);
    if(timing.clock_error || !timing.clock_calls) return -206;
    report[P_STAGE]=6;
    start=clock_now();
    result=flush_buffer();
    pair(P_FLUSH_LO,clock_now()-start);
    if(result) return result;
    report[P_STAGE]=7;
    if((result=photo_fs_finish())) return result;
    (void)phase_gpio_emit(8U);
    pair(P_FINISH_LO,clock_now()-start);
#if CAPTURE_DIAGNOSTICS
    start=clock_now();
    report[P_CHECKS_PERFORMED]|=SAVE_CHECK_POSTHASH;
    report[P_FNV_AFTER]=frame_fnv();
    pair(P_POSTHASH_LO,clock_now()-start);
    if(report[P_FNV_AFTER]!=report[P_FNV_BEFORE]) return -202;
#endif
    return 0;
}

int save_main(uint32_t raw_op, uint32_t mode)
{
    uint32_t bench=raw_op>>31, op=raw_op&0x7FFFFFFFU;
    const volatile save_request_t *request=(void *)SAVE_REQUEST_ADDRESS;
    uint32_t hz=25000000U, cache_owned=0;
    for(unsigned i=0;i<128;i++) report[i]=0;
    report[P_MAGIC]=SAVE_REPORT_MAGIC; report[P_SCHEMA]=SAVE_REPORT_SCHEMA; report[P_WORDS]=128;
    report[P_PROFILE]=CAPTURE_DIAGNOSTICS;
    report[P_STATE]=1; report[P_OP]=op; report[P_MODE]=mode;
    report[P_CPU_HZ]=SAVE_CLOCK_HZ; report[P_CCR]=SCB->CCR;
    report[P_INITIAL_MSPLIM]=__get_MSPLIM();
    report[P_BUFFER_ADDRESS]=(uint32_t)(op==SAVE_OP_READ ? scratch.read : output_buffer);
    report[P_BUFFER_BYTES]=op==SAVE_OP_READ ? sizeof(scratch.read) : sizeof(output_buffer);
    report[P_INITIAL_MPU_CTRL]=MPU->CTRL;
    report[P_CARD_SIZE]=sizeof(card); report[P_FS_SIZE]=sizeof(photo_fs_report_t);
    report[P_WIDTH]=SAVE_WIDTH; report[P_HEIGHT]=SAVE_HEIGHT;
    report[P_FRAME_BYTES]=SAVE_FRAME_BYTES;
    last_cycle=DWT->CYCCNT; report[P_BEGIN]=last_cycle;
    if(op==SAVE_OP_SAVE) (void)phase_gpio_emit(4U);
    int result=-203;
    if(SCB->CCR&SCB_CCR_DC_Msk) goto done;
    if(!(DWT->CTRL&DWT_CTRL_CYCCNTENA_Msk)) goto done;
    if(bench) {
        if(request->magic!=SAVE_REQUEST_MAGIC || request->operation!=op ||
           request->mode!=mode) goto done;
        hz=request->sd_clock_hz; report[P_NONCE]=request->nonce;
    } else if(op!=SAVE_OP_SAVE) goto done;
    if(mode>PNG16_FAST_SUB || op<SAVE_OP_SAVE || op>SAVE_OP_MOUNT) goto done;
    if(op==SAVE_OP_SAVE) {
        report[P_CHECKS_PERFORMED]|=SAVE_CHECK_FRAME;
        if(!frame_valid()) { result=-201; goto done; }
        const volatile uint32_t *profile=(void *)CAPTURE_PROFILE_ADDRESS;
        report[P_RECEIVER_FLAGS]=profile[CP_FLAGS];
        report[P_RECEIVER_FNV]=profile[CP_FNV];
    }
    /* This experiment uses the Arm default SRAM/device memory attributes.
     * Do not silently replace an inherited MPU configuration. The report and
     * request nonce above were published while D-cache was still disabled. */
    if(SAVE_DATA_CACHE && (MPU->CTRL&MPU_CTRL_ENABLE_Msk)) goto done;
    __DSB();
    if(SAVE_DATA_CACHE) {
        /* CMSIS invalidates all D-cache lines before enabling the cache. */
        SCB_EnableDCache();
        cache_owned=1;
        report[P_CACHE_ENABLED]=1;
    }
    /* The caller copied and CRC-checked code with D-cache disabled. */
    SCB_InvalidateICache(); SCB_EnableICache();
    status_led_set(STATUS_LED_NAND_WRITE);
    report[P_STAGE]=1;
    uint64_t start=clock_now();
    result=sd_init(&card,hz);
    pair(P_INIT_LO,clock_now()-start); report[P_SD_HZ]=card.clock_hz;
    if(result) goto done;
    if(op==SAVE_OP_SAVE) (void)phase_gpio_emit(5U);
    report[P_STAGE]=3; start=clock_now();
    result=op==SAVE_OP_FORMAT ? photo_fs_format(&card) : photo_fs_mount(&card);
    pair(P_MOUNT_LO,clock_now()-start);
    if(result) goto done;
    if(op==SAVE_OP_SAVE) (void)phase_gpio_emit(6U);
    if(op==SAVE_OP_SAVE) result=save_image((png16_mode)mode);
    else if(op==SAVE_OP_READ) {
        char name[16];
        for(unsigned i=0;i<16;i++) name[i]=request->name[i];
        name[15]=0;
        uint32_t got=0;
        if(request->length>sizeof(scratch.read)) result=-204;
        else result=photo_fs_readback(name,request->offset,scratch.read,request->length,&got);
        report[P_READ_BYTES]=got;
    }
done:
    /* A failed transfer is left powered; no reset/retry/erase is hidden here. */
    snapshot();
    if(!result) {
        report[P_STAGE]=8;
        uint64_t deinit_start=clock_now();
        result=sd_deinit(&card);
        pair(P_DEINIT_LO,clock_now()-deinit_start);
    }
    pair(P_TOTAL_LO,clock_now());
    report[P_END]=DWT->CYCCNT; report[P_RESULT]=(uint32_t)result;
    report[P_STATE]=result ? 3U : 2U;
    report[P_STACK_CANARY]=*(volatile uint32_t *)0x343A0000U;
    report[P_CHECKS_PERFORMED]|=SAVE_CHECK_CANARY;
    if(report[P_STACK_CANARY]!=0x5354414BU && !result) result=-205;
#if CAPTURE_DIAGNOSTICS
    uint64_t stack_start=clock_now();
    report[P_CHECKS_PERFORMED]|=SAVE_CHECK_STACK_SCAN;
    unsigned untouched=0;
    volatile uint32_t *stack=(void *)0x343A0000U;
    while(untouched<16384U && stack[untouched]==0x5354414BU) untouched++;
    report[P_STACK_USED]=65536U-untouched*4U;
    pair(P_STACK_SCAN_LO,clock_now()-stack_start);
#endif
    /* Progress above may be cached. Terminal is always zero until the entire
     * owned cache has been cleaned/invalidated and disabled. No DMA uses this
     * workspace; the camera has already stopped and SD accesses are CPU-polled.
     * An invalid caller that entered with D-cache on is rejected, never adopted. */
    uint64_t cleanup_start=clock_now();
    if(cache_owned) SCB_DisableDCache();
    pair(P_CLEANUP_LO,clock_now()-cleanup_start);
    report[P_CHECKS_PERFORMED]|=SAVE_CHECK_CACHE_CLEANUP;
    if(op==SAVE_OP_SAVE && frame_checked) {
        uint64_t check_start=clock_now();
        report[P_CHECKS_PERFORMED]|=SAVE_CHECK_FINAL_FRAME;
        if(!frame_valid() && !result) result=-201;
        pair(P_FINAL_CHECK_LO,clock_now()-check_start);
#if CAPTURE_DIAGNOSTICS
        uint64_t validate_start=clock_now();
        report[P_CHECKS_PERFORMED]|=SAVE_CHECK_POSTCLEAN_HASH;
        uint32_t value=frame_fnv();
        report[P_POSTCLEAN_FNV]=value;
        report[P_POSTCLEAN_VALIDATED]=(value==report[P_FNV_BEFORE]);
        pair(P_POSTCLEAN_VALIDATE_LO,clock_now()-validate_start);
        if(value!=report[P_FNV_BEFORE] && !result) result=-202;
#endif
    }
    snapshot();
    report[P_RESULT]=(uint32_t)result; report[P_STATE]=result ? 3U : 2U;
    status_led_set(result ? STATUS_LED_ERROR : STATUS_LED_OFF);
    SCB_DisableICache();
    __DSB(); __ISB();
    report[P_FINAL_CCR]=SCB->CCR;
    if(op==SAVE_OP_SAVE && !result) (void)phase_gpio_emit(9U);
    pair(P_COMPLETE_LO,clock_now());
    __DSB();
    report[P_TERMINAL]=0x444F4E45U;
    __DSB();
    return result;
}
