/* Compute only. No SD driver, filesystem, sensor, NOR commands or clock changes.
 * PREPARE moves execution/stack out of the future RAW upload before READY.
 * RUN proves the supplied fixture, times encoding, then publishes with caches off.
 */
#include <string.h>
#include "stm32n657xx.h"
#include "png16.h"
#include "bench_sink.h"

#ifdef PB_HOST_TEST
extern pb_report test_report;
extern pb_request test_request;
extern pb_chunk test_chunks[PB_MAX_CHUNKS];
extern uint8_t test_frame[PB_FRAME_BYTES];
extern uint32_t test_frame_guard[8],test_stack_guard;
#define REPORT (&test_report)
#define REQUEST (&test_request)
#define CHUNKS test_chunks
#define FRAME test_frame
#define FRAME_GUARD test_frame_guard
#define STACK_GUARD test_stack_guard
#else
#define REPORT ((volatile pb_report *)PB_REPORT_ADDRESS)
#define REQUEST ((const volatile pb_request *)PB_REQUEST_ADDRESS)
#define CHUNKS ((volatile pb_chunk *)PB_CHUNKS_ADDRESS)
#define FRAME ((const uint8_t *)PB_FRAME_ADDRESS)
#define FRAME_GUARD ((volatile uint32_t *)(PB_FRAME_ADDRESS+PB_FRAME_BYTES))
#define STACK_GUARD (*(volatile uint32_t *)PB_STACK_FLOOR)
#endif
static png16_workspace workspace __attribute__((aligned(32)));
static pb_sink sink;
static png16_stats stats;
static png16_timing timing;
static uint32_t last_tick;
static uint64_t ticks;
#ifndef PB_HOST_TEST
extern uint32_t _sbss[],_ebss[];
#endif

static uint64_t now(void *unused)
{
    (void)unused;
    uint32_t value=DWT->CYCCNT;
    ticks+=(uint32_t)(value-last_tick); last_tick=value;
    return ticks;
}

static void initialize(uint32_t operation)
{
#ifdef PB_HOST_TEST
    memset(&workspace,0,sizeof(workspace)); memset(&sink,0,sizeof(sink));
    memset(&stats,0,sizeof(stats)); memset(&timing,0,sizeof(timing));
#else
    for(uint32_t *p=_sbss;p<_ebss;p++) *p=0;
#endif
    volatile uint32_t *r=(volatile uint32_t *)REPORT;
    for(unsigned i=0;i<128;i++) r[i]=0;
    REPORT->magic=PB_MAGIC; REPORT->schema=1; REPORT->words=128;
    REPORT->state=PB_STATE_ACTIVE; REPORT->operation=operation;
    REPORT->nonce=REQUEST->nonce; REPORT->mode=REQUEST->mode;
    REPORT->cpu_hz=PB_CPU_HZ; REPORT->frame_address=PB_FRAME_ADDRESS;
    REPORT->frame_bytes=PB_FRAME_BYTES; REPORT->width=PB_WIDTH; REPORT->height=PB_HEIGHT;
    REPORT->initial_ccr=SCB->CCR; REPORT->initial_control=__get_CONTROL();
    REPORT->initial_mpu=MPU->CTRL; REPORT->initial_fpccr=FPU->FPCCR;
    last_tick=DWT->CYCCNT; ticks=0;
    STACK_GUARD=PB_CANARY;
}

static unsigned prerequisite(uint32_t operation)
{
    if(REQUEST->magic!=PB_MAGIC || REQUEST->schema!=1 || REQUEST->operation!=operation ||
       !REQUEST->nonce || REQUEST->mode>PB_MODE_MAX) return PB_BAD_REQUEST;
    for(unsigned i=0;i<8;i++) if(REQUEST->reserved[i]) return PB_BAD_REQUEST;
    if(operation==PB_ENCODE && (!REQUEST->output_bytes || REQUEST->output_bytes>PB_MAX_OUTPUT))
        return PB_BAD_REQUEST;
    if((SCB->CCR&(SCB_CCR_IC_Msk|SCB_CCR_DC_Msk)) || __get_CONTROL() ||
       __get_IPSR() || __get_PRIMASK()!=1 || __get_FAULTMASK() ||
       (FPU->FPCCR&1U) || (MPU->CTRL&MPU_CTRL_ENABLE_Msk)) return PB_BAD_CONTEXT;
    if ((SCB->CPACR&0x00F00000U)!=0x00F00000U) return PB_BAD_CONTEXT;
    REPORT->cfgr1=RCC->CFGR1; REPORT->cfgr2=RCC->CFGR2;
    if(RCC->CFGR1!=0x33330000U || RCC->CFGR2!=0x00100000U ||
       RCC->PLL1CFGR1!=0x00404B00U || RCC->PLL1CFGR2 || RCC->PLL1CFGR3!=0x49000005U ||
       (RCC->IC1CFGR&(RCC_IC1CFGR_IC1INT|RCC_IC1CFGR_IC1SEL))!=0x20000U ||
       (RCC->IC2CFGR&(RCC_IC2CFGR_IC2INT|RCC_IC2CFGR_IC2SEL))!=0x30000U ||
       !(RCC->DIVENR&RCC_DIVENR_IC2EN)) return PB_BAD_CLOCK;
    REPORT->ahb5enr=RCC->AHB5ENR; REPORT->ahb5rstr=RCC->AHB5RSTR;
    if((REPORT->ahb5enr&0x2020U)!=0x2020U || (REPORT->ahb5rstr&0x2020U) ||
       (REPORT->ahb5enr&RCC_AHB5ENR_SDMMC2EN)) return PB_BAD_STORAGE_CLOCK;
    /* Required clocks/reset verified above before reading the NOR controller. */
    REPORT->xspi_sr=XSPI1->SR;
    if(REPORT->xspi_sr&(XSPI_SR_BUSY|XSPI_SR_FLEVEL)) return PB_BAD_STORAGE_CLOCK;
    REPORT->dwt_ctrl=DWT->CTRL;
    if(!(DWT->CTRL&DWT_CTRL_CYCCNTENA_Msk)) return PB_BAD_DWT;
    uint32_t before=DWT->CYCCNT;
    for(unsigned i=0;i<32;i++) __NOP();
    REPORT->dwt_delta=DWT->CYCCNT-before;
    if(!REPORT->dwt_delta) return PB_BAD_DWT;
    return 0;
}

static uint32_t input_fnv(void)
{
    uint32_t value=2166136261U;
    for(unsigned i=0;i<PB_FRAME_BYTES;i++) value=(value^FRAME[i])*16777619U;
    return value;
}

static uint32_t guard_mask(void)
{
    uint32_t mask=0;
    for(unsigned i=0;i<8;i++) if(FRAME_GUARD[i]==0x504E4700U+i) mask|=1U<<i;
    return mask;
}

static void publish(unsigned result,uint32_t terminal)
{
    REPORT->final_ccr=SCB->CCR; REPORT->final_control=__get_CONTROL();
    REPORT->final_ipsr=__get_IPSR(); REPORT->final_primask=__get_PRIMASK();
    REPORT->final_faultmask=__get_FAULTMASK(); REPORT->final_fpccr=FPU->FPCCR;
    if((REPORT->final_ccr&(SCB_CCR_IC_Msk|SCB_CCR_DC_Msk)) || (REPORT->final_control&~12U) ||
       REPORT->final_ipsr || REPORT->final_primask!=1 || REPORT->final_faultmask ||
       (REPORT->final_fpccr&1U)) { if(!result) result=PB_BAD_FINAL_CONTEXT; }
    REPORT->stack_canary=STACK_GUARD;
    if(STACK_GUARD!=PB_CANARY && !result) result=PB_BAD_CANARY;
    REPORT->result=result; REPORT->state=result ? PB_STATE_FAILED : PB_STATE_OK;
    REPORT->complete_cycles=now(NULL);
    (void)terminal; /* Post-C assembly owns terminal publication. */
    __DSB();
}

void png_bench_prepare_main(void)
{
    initialize(PB_PREPARE);
    unsigned result=prerequisite(PB_PREPARE);
    REPORT->stage=result ? 1U : 2U;
    publish(result,PB_READY);
}

void png_bench_run_main(void)
{
    initialize(PB_ENCODE);
    unsigned result=prerequisite(PB_ENCODE),owned=0;
    if(result) goto done;
    REPORT->stage=3;
    uint64_t start=now(NULL);
    REPORT->input_fnv_before=input_fnv();
    REPORT->input_check_cycles=now(NULL)-start;
    REPORT->frame_canary_mask=guard_mask();
    if(REPORT->input_fnv_before!=REQUEST->input_fnv) { result=PB_BAD_INPUT; goto done; }
    if(REPORT->frame_canary_mask!=255) { result=PB_BAD_CANARY; goto done; }
    /* All cache ownership starts here, after an uncached fresh report and nonce. */
    __DSB(); SCB_EnableDCache(); owned=1; REPORT->cache_owned=1;
    SCB_InvalidateICache(); SCB_EnableICache();
    REPORT->stage=4;
    start=now(NULL);
    pb_sink_init(&sink,now,NULL,CHUNKS,start,PB_MAX_CYCLES);
    png16_timing_config config={now,NULL,&timing};
    int encoded=png16_encode_timed(FRAME,PB_FRAME_BYTES,PB_WIDTH,PB_HEIGHT,PB_WIDTH*2U,
        (png16_mode)REQUEST->mode,&workspace,sizeof(workspace),pb_sink_write,&sink,&stats,&config);
    uint64_t end=now(NULL);
    REPORT->encode_cycles=end-start; REPORT->sink_body_cycles=sink.sink_cycles;
    REPORT->sink_cycles=timing.callback_cycles;
    REPORT->cpu_cycles=end-start>=timing.callback_cycles ? end-start-timing.callback_cycles : 0;
    REPORT->encoder_result=(uint32_t)encoded;
    (void)pb_sink_finish(&sink,end);
    REPORT->output_bytes=sink.bytes; REPORT->output_fnv=sink.fnv;
    REPORT->callback_calls=sink.calls; REPORT->chunk_count=sink.chunk_count;
    REPORT->rows=stats.rows_encoded; REPORT->idat_chunks=stats.idat_chunks;
    REPORT->png_total=timing.total_cycles; REPORT->png_conversion=timing.conversion_cycles;
    REPORT->png_deflate=timing.deflate_cycles; REPORT->png_framing=timing.framing_cycles;
    REPORT->png_callback=timing.callback_cycles; REPORT->png_other=timing.other_cycles;
    REPORT->png_clock_calls=timing.clock_calls; REPORT->png_clock_error=timing.clock_error;
    REPORT->timed_out=sink.error==PB_TIMEOUT;
    if(sink.error) result=sink.error;
    else if(encoded) result=PB_ENCODER_FAILED;
    else if(stats.output_bytes!=sink.bytes || stats.callback_calls!=sink.calls ||
            stats.rows_encoded!=PB_HEIGHT || timing.clock_error || end-start<timing.callback_cycles ||
            timing.callback_cycles<sink.sink_cycles)
        result=PB_BAD_STATS;
    else if(sink.bytes!=REQUEST->output_bytes || sink.fnv!=REQUEST->output_fnv) result=PB_BAD_OUTPUT;
    REPORT->stage=5;
done:
    if(owned) {
        uint64_t cleanup_start=now(NULL);
        SCB_DisableDCache(); SCB_DisableICache(); __DSB(); __ISB();
        REPORT->cleanup_cycles=now(NULL)-cleanup_start;
        uint64_t check_start=now(NULL);
        REPORT->input_fnv_after=input_fnv(); REPORT->frame_canary_mask=guard_mask();
        REPORT->final_check_cycles=now(NULL)-check_start;
        if(REPORT->input_fnv_after!=REPORT->input_fnv_before && !result) result=PB_BAD_INPUT;
        if(REPORT->frame_canary_mask!=255 && !result) result=PB_BAD_CANARY;
    }
    publish(result,PB_DONE);
}
