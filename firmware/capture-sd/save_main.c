/* Post-capture storage module and explicit, guarded RAM bench operations. */
#include <string.h>
#include "stm32n6xx.h"
#include "status_leds.h"
#include "save_protocol.h"
#include "photo_fs.h"
#include "png16.h"

static sd_card_t card;
static png16_workspace workspace;
static uint8_t output_buffer[SAVE_BUFFER_BYTES] __attribute__((aligned(32)));
static uint32_t buffered, last_cycle;
static uint64_t elapsed, callback_cycles;
static volatile uint32_t *const report=(volatile uint32_t *)SAVE_REPORT_ADDRESS;

static uint64_t clock_now(void)
{
    uint32_t now=DWT->CYCCNT;
    elapsed+=(uint32_t)(now-last_cycle);
    last_cycle=now;
    return elapsed;
}
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
static uint32_t frame_fnv(void)
{
    const uint8_t *p=(const uint8_t *)SAVE_FRAME_ADDRESS;
    uint32_t value=2166136261U;
    for(unsigned i=0;i<SAVE_FRAME_BYTES;i++) value=(value^p[i])*16777619U;
    return value;
}
static int frame_valid(void)
{
    const volatile uint32_t *trace=(void *)0x343F0000U;
    const volatile uint32_t *raw=(void *)0x343F6000U;
    const volatile uint32_t *guard=(void *)(SAVE_FRAME_ADDRESS+SAVE_FRAME_BYTES);
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
    if(!frame_valid()) return -201;
    report[P_FNV_BEFORE]=frame_fnv();
    if(report[P_FNV_BEFORE]!=((volatile uint32_t *)0x343F0000U)[11]) return -202;
    pair(P_VALIDATE_LO,clock_now()-start);
    report[P_STAGE]=4;
    int result=photo_fs_open(SAVE_MAX_PNG_BYTES);
    if(result) return result;
    snapshot();
    report[P_STAGE]=5;
    png16_stats stats={0};
    start=clock_now();
    int png_result=png16_encode((const void *)SAVE_FRAME_ADDRESS,SAVE_FRAME_BYTES,
        SAVE_WIDTH,SAVE_HEIGHT,SAVE_WIDTH*2U,mode,workspace.bytes,sizeof(workspace),
        append_png,0,&stats);
    pair(P_ENCODE_LO,clock_now()-start);
    pair(P_CALLBACK_LO,callback_cycles);
    pair(P_PNG_BYTES_LO,stats.output_bytes);
    report[P_ROWS]=stats.rows_encoded; report[P_IDAT_CHUNKS]=stats.idat_chunks;
    report[P_CALLBACKS]=stats.callback_calls; report[P_PNG_RESULT]=(uint32_t)png_result;
    if(png_result) return png_result;
    report[P_STAGE]=6;
    start=clock_now();
    if((result=flush_buffer())) return result;
    report[P_STAGE]=7;
    if((result=photo_fs_finish())) return result;
    pair(P_FINISH_LO,clock_now()-start);
    report[P_FNV_AFTER]=frame_fnv();
    if(report[P_FNV_AFTER]!=report[P_FNV_BEFORE]) return -202;
    return 0;
}

int save_main(uint32_t raw_op, uint32_t mode)
{
    uint32_t bench=raw_op>>31, op=raw_op&0x7FFFFFFFU;
    const volatile save_request_t *request=(void *)SAVE_REQUEST_ADDRESS;
    uint32_t hz=25000000U;
    for(unsigned i=0;i<128;i++) report[i]=0;
    report[P_MAGIC]=SAVE_REPORT_MAGIC; report[P_SCHEMA]=1; report[P_WORDS]=128;
    report[P_STATE]=1; report[P_OP]=op; report[P_MODE]=mode;
    report[P_CPU_HZ]=SAVE_CLOCK_HZ; report[P_CCR]=SCB->CCR;
    report[P_INITIAL_MSPLIM]=__get_MSPLIM();
    report[P_BUFFER_ADDRESS]=(uint32_t)output_buffer;
    report[P_BUFFER_BYTES]=sizeof(output_buffer);
    report[P_CARD_SIZE]=sizeof(card); report[P_FS_SIZE]=sizeof(photo_fs_report_t);
    report[P_WIDTH]=SAVE_WIDTH; report[P_HEIGHT]=SAVE_HEIGHT;
    report[P_FRAME_BYTES]=SAVE_FRAME_BYTES;
    last_cycle=DWT->CYCCNT; report[P_BEGIN]=last_cycle;
    int result=-203;
    if(SCB->CCR&SCB_CCR_DC_Msk) goto done;
    if(!(DWT->CTRL&DWT_CTRL_CYCCNTENA_Msk)) goto done;
    if(bench) {
        if(request->magic!=SAVE_REQUEST_MAGIC || request->operation!=op ||
           request->mode!=mode) goto done;
        hz=request->sd_clock_hz; report[P_NONCE]=request->nonce;
    } else if(op!=SAVE_OP_SAVE) goto done;
    if(mode>PNG16_FAST_SUB || op<SAVE_OP_SAVE || op>SAVE_OP_MOUNT) goto done;
    if(op==SAVE_OP_SAVE && !frame_valid()) { result=-201; goto done; }
    /* The caller copied and CRC-checked code with D-cache disabled. */
    SCB_InvalidateICache(); SCB_EnableICache();
    status_led_set(STATUS_LED_NAND_WRITE);
    report[P_STAGE]=1;
    uint64_t start=clock_now();
    result=sd_init(&card,hz);
    pair(P_INIT_LO,clock_now()-start); report[P_SD_HZ]=card.clock_hz;
    if(result) goto done;
    report[P_STAGE]=3; start=clock_now();
    result=op==SAVE_OP_FORMAT ? photo_fs_format(&card) : photo_fs_mount(&card);
    pair(P_MOUNT_LO,clock_now()-start);
    if(result) goto done;
    if(op==SAVE_OP_SAVE) result=save_image((png16_mode)mode);
    else if(op==SAVE_OP_READ) {
        char name[16];
        for(unsigned i=0;i<16;i++) name[i]=request->name[i];
        name[15]=0;
        uint32_t got=0;
        if(request->length>sizeof(output_buffer)) result=-204;
        else result=photo_fs_readback(name,request->offset,output_buffer,request->length,&got);
        report[P_READ_BYTES]=got;
    }
done:
    /* A failed transfer is left powered; no reset/retry/erase is hidden here. */
    snapshot();
    if(!result) {
        report[P_STAGE]=8;
        result=sd_deinit(&card);
    }
    pair(P_TOTAL_LO,clock_now());
    report[P_END]=DWT->CYCCNT; report[P_RESULT]=(uint32_t)result;
    report[P_STATE]=result ? 3U : 2U;
    report[P_STACK_CANARY]=*(volatile uint32_t *)0x343A0000U;
    unsigned untouched=0;
    volatile uint32_t *stack=(void *)0x343A0000U;
    while(untouched<16384U && stack[untouched]==0x5354414BU) untouched++;
    report[P_STACK_USED]=65536U-untouched*4U;
    snapshot();
    status_led_set(result ? STATUS_LED_ERROR : STATUS_LED_OFF);
    SCB_DisableICache();
    __DSB(); __ISB();
    report[P_TERMINAL]=0x444F4E45U;
    __DSB();
    return result;
}
