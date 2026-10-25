/* One-owner packed capture/RAW-sector coordinator. No filesystem or encoder.
 * Camera and SD controllers operate independently; only completed immutable
 * prefixes may become SD sources. The default uses the hardware-tested complete
 * frame path; optional LINE uses one group of holdback. Neither infers a live
 * producer pointer from the frame-latched P0DCCNTR. */
#include "stm32n6xx_hal.h"
#include "status_leds.h"
#include "phase_gpio.h"
#include "runtime.h"
#define Q ((volatile const uint32_t *)RAW_REQUEST_ADDRESS)
#define P ((volatile uint32_t *)RAW_PROOF_ADDRESS)
#define TRACE ((volatile const uint32_t *)0x343F0000U)
#define RAW10 ((volatile const uint32_t *)0x343F6000U)
#define SENSOR ((volatile const uint32_t *)0x343F4000U)
#define DATA_OFF ((volatile const uint32_t *)0x343F8900U)
#define ABORT ((volatile uint32_t *)RAW_ABORT_ADDRESS)
#ifndef RAW_FLASH
#define RAW_FLASH 0
#endif
#ifndef RAW_STANDBY
#define RAW_STANDBY 0
#endif
#ifndef RAW_PATTERN
#define RAW_PATTERN 0
#endif
#ifndef RAW_DMA
#define RAW_DMA 1
#endif
#ifndef RAW_CHUNK_SECTORS
#define RAW_CHUNK_SECTORS 1024U
#endif
#ifndef RAW_ASYNC_STOP
#define RAW_ASYNC_STOP 0
#endif
#ifndef RAW_DMA_SLEEP
#define RAW_DMA_SLEEP 0
#endif
#ifndef RAW_SD_CLOCK_HZ
#define RAW_SD_CLOCK_HZ 25000000U
#endif
#if RAW_SD_CLOCK_HZ != 12500000U && RAW_SD_CLOCK_HZ != 25000000U
#error Unsupported RAW SD clock
#endif
#if SD_GPIO_SPEED != 3 && (RAW_FLASH || RAW_STANDBY)
#error Nondefault SD GPIO speed is RAM diagnostic only
#endif
#if (SD_GPIO_SPEED == 1 || SD_GPIO_SPEED == 2) && RAW_SD_CLOCK_HZ != 25000000U
#error Intermediate GPIO speed is a 25 MHz diagnostic only
#endif
#if SD_FIXED_COMPENSATION && (RAW_FLASH || RAW_STANDBY || RAW_SD_CLOCK_HZ != 25000000U)
#error Fixed compensation is an isolated 25 MHz RAM diagnostic only
#endif
#if SD_CLOCK_NEGEDGE && RAW_SD_CLOCK_HZ != 25000000U
#error Clock phase requires 25 MHz
#endif
sd_card_t raw_card;
raw_slots_t raw_slots;
#if RAW_MAGIC_FORMAT
magic_slots_t raw_magic_slots;
sd_scr_t raw_scr;
sd_stream_t raw_stream;
sd_erase_t raw_erase;
volatile uint32_t raw_magic_proof[8];
#endif
#if RAW_WHOLE_IMAGE_PREERASE
/* magic,state,true-boundary faults,post-pad faults,valid,padded,pad,sectors.
 * Original guard is validated before conversion to zero padding; the distinct
 * guard after the sector allocation remains live throughout DMA and commit. */
volatile uint32_t raw_whole_proof[8];
#endif
#if RAW_DMA_SLEEP
sd_dma_wait_t raw_dma_wait;
/* 0..7: memory/RIF/SD clocks before+after, configured, readback faults.
 * 8/9: BUSLP before/after; 10/11: debug clock/reset; 12/13: DBGCR before/after. */
volatile uint32_t raw_dma_sleep_clocks[14];
_Static_assert(sizeof(sd_dma_wait_t)==24U,"Update the wait-proof manifest when its ABI changes");
#endif
static uint32_t operation, capture_active, storage_call_depth;
/* SD callbacks may service bounded asynchronous STOP, but LINE mode defers
 * full post-frame validation/fail parks until all SD calls have returned. */
#define SD_OPERATION(result, expression) do { \
    storage_call_depth++; (result)=(expression); storage_call_depth--; \
} while(0)
uint32_t raw_storage_transfer_active(void) { return storage_call_depth; }
extern int stage1_sensor_start(void);
extern void status_led_complete_sleep(void) __attribute__((noreturn));
static void terminal(uint32_t result) __attribute__((noreturn,noinline,used));
static void complete_storage(int result) __attribute__((noreturn));

/* Failure-only camera isolation. Never calls I2C/HAL, waits for a frame, reads a
 * gated camera register, or touches SD clocks, reset, pins or ownership. Dedicated
 * sensor/receiver resets discard the failed frame; this is not the successful
 * idle-checked STOP sequence and does not establish SD idle or AXI-drain proof.
 * Normal callers are between SD calls; unexpected nested/ISR failures are
 * explicitly refused in the record, with SD ownership retained. */
static void abort_camera(uint32_t reason)
{
    if(operation!=RAW_OP_CAPTURE || ABORT[0]==RAW_ABORT_MAGIC) return;
    uint32_t primask=__get_PRIMASK();
    __disable_irq();
    ABORT[0]=RAW_ABORT_MAGIC; ABORT[1]=1U; ABORT[2]=1U;
    ABORT[3]=reason; ABORT[6]=storage_call_depth; ABORT[7]=DWT->CYCCNT;
    ABORT[15]=(storage_call_depth?1U:0U)|(__get_IPSR()?2U:0U);
    capture_active=0;
    NVIC_DisableIRQ(CSI_IRQn); NVIC_DisableIRQ(DCMIPP_IRQn);
    ABORT[9]=RCC->APB5RSTR;
    RCC->APB5RSTSR=RCC_APB5RSTSR_DCMIPPRSTS|RCC_APB5RSTSR_CSIRSTS;
    __DSB(); ABORT[10]=RCC->APB5RSTR;
    if((ABORT[10]&(RCC_APB5RSTR_DCMIPPRST|RCC_APB5RSTR_CSIRST))!=
       (RCC_APB5RSTR_DCMIPPRST|RCC_APB5RSTR_CSIRST)) ABORT[15]|=16U;
    RCC->AHB4ENSR=RCC_AHB4ENSR_GPIOOENS; (void)RCC->AHB4ENR;
    if((RCC->AHB4ENR&RCC_AHB4ENR_GPIOOEN) &&
       !(RCC->AHB4RSTR&RCC_AHB4RSTR_GPIOORST)) {
        /* Camera RESET is PO5. Set its latch before making it push-pull output. */
        GPIOO->BSRR=1U<<21; GPIOO->OTYPER&=~(1U<<5);
        GPIOO->PUPDR&=~(3U<<10);
        GPIOO->MODER=(GPIOO->MODER&~(3U<<10))|(1U<<10);
        __DSB();
        ABORT[11]=GPIOO->MODER; ABORT[12]=GPIOO->ODR; ABORT[13]=GPIOO->IDR;
        if((ABORT[11]&(3U<<10))!=(1U<<10) ||
           ((ABORT[12]|ABORT[13])&(1U<<5))) ABORT[15]|=8U;
    } else ABORT[15]|=4U;
    NVIC_ClearPendingIRQ(CSI_IRQn); NVIC_ClearPendingIRQ(DCMIPP_IRQn);
    ABORT[8]=DWT->CYCCNT; ABORT[2]=ABORT[15]?15U:2U;
    __DSB(); __set_PRIMASK(primask);
}

void raw_capture_fail(uint32_t where,int32_t result)
{
    ABORT[4]=where; ABORT[5]=(uint32_t)result;
#if RAW_FLASH
    /* Prepare/arm and the checked loader can fail before storage code exists.
     * No SD operation has begun at that point. Never enter an unloaded helper. */
    if(*(volatile const uint32_t *)0x343F9E3CU!=0x524C4F4BU) {
        if(raw_card.initialized || raw_card.controller_owned || storage_call_depth)
            terminal(0xF003U); /* unexpected ownership stays visible/untouched */
        terminal(0x600U|(where&255U));
    }
#endif
    complete_storage(0x600U|(where&255U));
}

static void snapshot(void)
{
#if RAW_MAGIC_FORMAT
    /* Compatibility mirror for the common ownership report. No old header or
     * generation is written to media in magic mode. */
    raw_slots.card=&raw_card;
    raw_slots.selected_slot=raw_magic_slots.selected_slot;
    raw_slots.payload_lba=raw_magic_slots.slot_lba;
    raw_slots.slot_count=raw_magic_slots.slot_count;
    raw_slots.written_sectors=raw_magic_slots.written_sectors;
    raw_slots.scan_headers=raw_magic_slots.scan_headers;
    raw_slots.opened=raw_magic_slots.opened;
    raw_slots.active=raw_magic_slots.active;
    raw_slots.error=raw_magic_slots.error;
#endif
    P[RP_CAPTURE_ERROR]=operation==RAW_OP_CAPTURE?raw_capture_fault():0U;
    P[RP_CARD]=(uint32_t)&raw_card; P[RP_CARD_SIZE]=sizeof(raw_card);
    P[RP_SLOTS]=(uint32_t)&raw_slots; P[RP_SLOTS_SIZE]=sizeof(raw_slots);
    P[RP_SD_ERROR]=raw_card.error; P[RP_MEDIA_IDLE]=raw_card.media_idle;
    P[RP_INITIALIZED]=raw_card.initialized;
    P[RP_CONTROLLER_OWNED]=raw_card.controller_owned;
    P[RP_LAST_READY]=raw_card.last_ready_r1; P[RP_CLEANUP_ERROR]=raw_card.cleanup_error;
    P[RP_SLOT]=raw_slots.selected_slot; P[RP_PAYLOAD_LBA]=raw_slots.payload_lba;
    P[RP_SLOT_COUNT]=raw_slots.slot_count; P[RP_WRITTEN_SECTORS]=raw_slots.written_sectors;
    P[RP_SCAN_HEADERS]=raw_slots.scan_headers; P[RP_FORMATTED_SLOTS]=raw_slots.formatted_slots;
    P[RP_CARD_READ_LO]=(uint32_t)raw_card.read_sectors;
    P[RP_CARD_READ_HI]=(uint32_t)(raw_card.read_sectors>>32);
    P[RP_CARD_WRITE_LO]=(uint32_t)raw_card.written_sectors;
    P[RP_CARD_WRITE_HI]=(uint32_t)(raw_card.written_sectors>>32);
    P[RP_WRITE_CYCLES_LO]=(uint32_t)raw_card.write_cycles;
    P[RP_WRITE_CYCLES_HI]=(uint32_t)(raw_card.write_cycles>>32);
    P[RP_READY_CYCLES_LO]=(uint32_t)raw_card.ready_cycles;
    P[RP_READY_CYCLES_HI]=(uint32_t)(raw_card.ready_cycles>>32);
    P[RP_INIT_CYCLES]=raw_card.init_cycles; P[RP_CLOCK_HZ]=raw_card.clock_hz;
    P[RP_GENERATION_LO]=(uint32_t)raw_slots.generation;
    P[RP_GENERATION_HI]=(uint32_t)(raw_slots.generation>>32);
}

/* Progress never calls the SD API, and never changes controller ownership.
 * The bounded camera STOP/I2C work may run inside card initialization waits.
 * LINE may issue only its published immutable prefixes before full validation.
 * Full post-frame checks are deferred until the outer SD call returns. */
void sd_progress(void)
{
    if(capture_active) raw_capture_poll();
    snapshot();
}

static void configure_sd_master(void)
{
    __HAL_RCC_RIFSC_CLK_ENABLE();
    (void)RCC->AHB3ENR;
    /* RIFSC has an AHB3 enable, but no software reset bit in this device. */
    if(!(RCC->AHB3ENR&RCC_AHB3ENR_RIFSCEN)) terminal(0x210U);
    RIMC_MasterConfig_t before={0},after={0};
    RIMC_MasterConfig_t m={.MasterCID=RIF_CID_1,
        .SecPriv=RIF_ATTRIBUTE_SEC|RIF_ATTRIBUTE_PRIV};
    /* RM0486 6.3.4: a nonsecure SDMMC2 configuration port forces its DMA
     * requests nonsecure, overriding the master's MSEC attribute. Configure
     * this peripheral (RISUP54) explicitly; never relax SRAM RISAF protection. */
    if(HAL_RIF_RISC_GetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_SDMMC2)!=m.SecPriv) {
        if(HAL_RIF_RISC_GetLock() ||
           HAL_RIF_RISC_GetSlaveConfigLock(RIF_RISC_PERIPH_INDEX_SDMMC2)) terminal(0x213U);
        HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_SDMMC2,m.SecPriv);
    }
    if(HAL_RIF_RISC_GetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_SDMMC2)!=m.SecPriv)
        terminal(0x214U);
    HAL_RIF_RIMC_GetConfigMasterAttributes(RIF_MASTER_INDEX_SDMMC2,&before);
    if(before.MasterCID!=m.MasterCID || before.SecPriv!=m.SecPriv) {
        if(HAL_RIF_RIMC_GetLock()) terminal(0x211U);
        HAL_RIF_RIMC_ConfigMasterAttributes(RIF_MASTER_INDEX_SDMMC2,&m);
    }
    HAL_RIF_RIMC_GetConfigMasterAttributes(RIF_MASTER_INDEX_SDMMC2,&after);
    if(after.MasterCID!=m.MasterCID || after.SecPriv!=m.SecPriv) terminal(0x212U);
}

__attribute__((noreturn,noinline,used)) static void terminal(uint32_t result)
{
    if(result) abort_camera(result);
    snapshot(); P[RP_RESULT]=result; P[RP_END]=DWT->CYCCNT;
    capture_active=0;
    status_led_set(result?STATUS_LED_ERROR:STATUS_LED_OFF);
    __disable_irq(); SysTick->CTRL=0; SysTick->VAL=0;
    SCB->ICSR=SCB_ICSR_PENDSTCLR_Msk|SCB_ICSR_PENDSVCLR_Msk;
    /* Nonreturning top-level image owns HAL clock calculation FP state. */
    P[RP_CONTEXT_BEFORE]=__get_CONTROL(); P[RP_FPCCR_BEFORE]=FPU->FPCCR;
    P[RP_CPACR_BEFORE]=SCB->CPACR; P[RP_MSPLIM]=__get_MSPLIM(); P[RP_MSP]=__get_MSP();
    if((SCB->CCR&SCB_CCR_DC_Msk) || (__get_CONTROL()&~0xCU) ||
       (FPU->FPCCR&1U) || __get_IPSR() || __get_FAULTMASK() ||
       __get_MSPLIM()!=0x343AF000U || __get_MSP()<=0x343AF000U ||
       __get_MSP()>0x343B0000U) {
        P[RP_RESULT]=0xF001U; P[RP_STATE]=15U; __DSB();
        __asm volatile(".global raw_context_refused_park\nraw_context_refused_park:\nb.n .\n");
        __builtin_unreachable();
    }
    SCB_DisableICache(); SCB_InvalidateICache();
    __asm volatile("movs r0,#0\nmsr CONTROL,r0\ndsb 0xF\nisb 0xF\n":::"r0","memory");
    SCB->CPACR=0; __DSB(); __ISB();
    P[RP_CCR]=SCB->CCR; P[RP_CONTROL]=__get_CONTROL();
    P[RP_IPSR]=__get_IPSR(); P[RP_PRIMASK]=__get_PRIMASK();
    P[RP_FPCCR]=FPU->FPCCR; P[RP_CPACR]=SCB->CPACR; P[RP_SYSTICK]=SysTick->CTRL;
    P[RP_STATE]=result?15U:3U;
    __DSB(); P[RP_TERMINAL]=RAW_PROOF_TERMINAL; __DSB(); __ISB();
#if RAW_STANDBY
    if(!result && operation==RAW_OP_CAPTURE) status_led_complete_sleep();
#endif
    __asm volatile(".global raw_terminal_park\nraw_terminal_park:\nb.n .\n");
    __builtin_unreachable();
}

static void complete_storage(int result)
{
    if(result) abort_camera((uint32_t)result);
    capture_active=0;
    /* Never recurse into SD or deinitialize an unreturned controller operation. */
    if(storage_call_depth || __get_IPSR()) terminal(0xF002U);
    if(raw_card.initialized && raw_card.controller_owned) {
        int cleanup; SD_OPERATION(cleanup,sd_deinit(&raw_card));
        if(!result) result=cleanup;
        if(!cleanup) {
            P[RP_DEINIT_DONE]=DWT->CYCCNT;
            if(operation==RAW_OP_CAPTURE) (void)phase_gpio_emit(9U);
        }
    }
    terminal((uint32_t)result);
}

static void init_card(void)
{
    P[RP_STAGE]=2U; P[RP_SD_BEGIN]=DWT->CYCCNT;
    if(operation==RAW_OP_CAPTURE) (void)phase_gpio_emit(4U);
    configure_sd_master();
    int r; SD_OPERATION(r,sd_init(&raw_card,RAW_SD_CLOCK_HZ));
    if(r) complete_storage(0x200U|(uint32_t)r);
    P[RP_SD_READY]=DWT->CYCCNT;
    if(operation==RAW_OP_CAPTURE) (void)phase_gpio_emit(5U);
}

static void sensor_reset_start(void)
{
#if !RAW_FLASH
    RCC->AHB4ENSR=RCC_AHB4ENSR_GPIODENS|RCC_AHB4ENSR_GPIOEENS;
    (void)RCC->AHB4ENR;
    GPIOD->MODER=(GPIOD->MODER&~3U)|1U; GPIOE->MODER=(GPIOE->MODER&~3U)|1U;
    GPIOE->BSRR=1U<<16; GPIOD->BSRR=1U;
    volatile uint32_t *trace=(volatile uint32_t *)0x343F0000U;
    for(unsigned i=0;i<64;++i) trace[i]=0;
    trace[0]=0x43545031U; trace[16]=RCC->CFGR1; trace[17]=RCC->CFGR2;
    trace[18]=SCB->CCR; trace[19]=BSEC->DBGCR; trace[20]=BSEC->AP_UNLOCK;
    RCC->AHB4ENSR=RCC_AHB4ENSR_PWRENS|RCC_AHB4ENSR_GPIOOENS;
    (void)RCC->AHB4ENR; PWR->SVMCR3|=PWR_SVMCR3_VDDIO2SV;
    GPIOO->BSRR=1U<<21; GPIOO->OTYPER&=~(1U<<5);
    GPIOO->PUPDR&=~(3U<<10); GPIOO->OSPEEDR|=3U<<10;
    GPIOO->MODER=(GPIOO->MODER&~(3U<<10))|(1U<<10);
    P[RP_SENSOR_RESET_BEGIN]=DWT->CYCCNT;
    while((uint32_t)(DWT->CYCCNT-P[RP_SENSOR_RESET_BEGIN])<40800U) __NOP();
    GPIOO->BSRR=1U<<5; P[RP_SENSOR_RESET_END]=DWT->CYCCNT;
    int r=stage1_sensor_start();
    if(r) terminal(0x100U|SENSOR[1]);
#endif
    P[RP_SENSOR_START_BEGIN]=SENSOR[4]; P[RP_SENSOR_START_END]=SENSOR[5];
}

void raw_runtime_dispatch(void)
{
#if RAW_FLASH
    /* Fixed diagnostic SRAM is outside .bss and may survive a warm reset.
     * Revoke the previous boot's late-code authority before any early failure.
     * Only this boot's checked raw_late_load() may publish RLOK again. */
    *(volatile uint32_t *)0x343F9E3CU=0U;
    __DSB();
#endif
#if RAW_WHOLE_IMAGE_PREERASE
    for(unsigned i=0;i<8U;++i) raw_whole_proof[i]=0;
#endif
#if RAW_MAGIC_FORMAT
    for(unsigned i=0;i<8U;++i) raw_magic_proof[i]=0;
#endif
    for(unsigned i=0;i<RAW_PROOF_WORDS;++i) P[i]=0;
    for(unsigned i=0;i<RAW_ABORT_WORDS;++i) ABORT[i]=0;
    operation=RAW_FLASH?RAW_OP_CAPTURE:Q[2];
    P[RP_MAGIC]=RAW_PROOF_MAGIC; P[RP_SCHEMA]=1; P[RP_WORDS]=RAW_PROOF_WORDS;
    P[RP_NONCE]=RAW_FLASH?0:Q[1]; P[RP_OPERATION]=operation;
    P[RP_STATE]=1; P[RP_RESULT]=0xFFFFFFFFU; P[RP_STAGE]=1;
    P[RP_FRAME]=RAW_FRAME_ADDRESS; P[RP_BYTES]=RAW_SLOTS_PAYLOAD_BYTES;
    P[RP_WIDTH]=RAW_SLOTS_WIDTH; P[RP_HEIGHT]=RAW_SLOTS_HEIGHT;
    P[RP_PATTERN]=RAW_PATTERN; P[RP_BEGIN]=DWT->CYCCNT;
    P[RP_TRANSPORT]=RAW_DMA; P[RP_CHUNK_SECTORS]=RAW_CHUNK_SECTORS;
    P[RP_COMPLETION]=RAW_STANDBY;
    P[RP_FLAGS]=(RAW_ASYNC_STOP?1U:0U)|(RAW_LINE_STREAM?2U:0U)|
        (RAW_PREINIT?4U:0U)|(RAW_LINE_SNAPSHOTS?8U:0U)|(RAW_LINE_POISON?16U:0U)|
        (RAW_DMA_SLEEP?32U:0U)|(RAW_WHOLE_IMAGE_PREERASE?64U:0U)|(RAW_MAGIC_FORMAT?128U:0U);
#if RAW_DMA_SLEEP
    raw_dma_wait.milliseconds=HAL_GetTick;
#endif
    raw_producer_init(&raw_producer,RAW_LINE_STREAM);
    if(!RAW_FLASH && (Q[0]!=RAW_REQUEST_MAGIC || !Q[1] ||
       operation<RAW_OP_CAPTURE || operation>RAW_OP_READ)) terminal(1);
    if(__get_CONTROL() || __get_IPSR() || __get_PRIMASK()!=1U ||
       (SCB->CCR&SCB_CCR_DC_Msk) || __get_FAULTMASK() || (FPU->FPCCR&1U)) terminal(2);
    status_led_boot_begin(); status_led_proof_init();
    if(operation==RAW_OP_CAPTURE) {
#if RAW_PREINIT
        /* Diagnostic only: card readiness before sensor START forces genuine
         * acquisition/write overlap; this is not a normal cold-start timing. */
        SystemCoreClockUpdate();
        if(!phase_gpio_init()) terminal(0x213U);
        init_card();
#endif
#if RAW_LINE_POISON
        volatile uint32_t *frame=(volatile uint32_t *)RAW_FRAME_ADDRESS;
        for(uint32_t i=0;i<RAW_SLOTS_PAYLOAD_BYTES/4U;i++) frame[i]=0xA5A5A5A5U;
        __DSB();
#endif
        sensor_reset_start(); return;
    }
    SystemCoreClockUpdate();
    init_card();
    int r;
    if(operation==RAW_OP_FORMAT) {
        P[RP_STAGE]=3U;
#if RAW_MAGIC_FORMAT
        if(Q[3] || Q[4] || Q[5]) complete_storage(3);
        SD_OPERATION(r,sd_read_scr(&raw_card,&raw_scr));
        if(r) complete_storage(0x300U|(uint32_t)r);
        r=magic_slots_open(&raw_magic_slots,&raw_card,raw_scr.erased_byte);
        if(r) complete_storage(0x310U|(uint32_t)r);
        SD_OPERATION(r,sd_erase_all(&raw_card,600000U,&raw_erase));
        if(!r) raw_slots.formatted_slots=raw_magic_slots.slot_count;
#else
        SD_OPERATION(r,raw_slots_format(&raw_slots,&raw_card,Q[3],Q[4],Q[5]));
#endif
        if(r) complete_storage(0x300U|(uint32_t)r);
    } else {
        /* Raw block reads are explicit and cannot touch the retained frame. */
        uint32_t lba=Q[3],count=Q[4];
        if(!count || count>RAW_READ_MAX_BYTES/512U) complete_storage(3);
        P[RP_STAGE]=4U; P[RP_READ_LBA]=lba; P[RP_READ_COUNT]=count;
        P[RP_READ_DEST]=RAW_READ_ADDRESS;
        SD_OPERATION(r,sd_read_blocks(&raw_card,lba,(void *)RAW_READ_ADDRESS,count));
        if(r) complete_storage(0x400U|(uint32_t)r);
        P[RP_READ_BYTES]=count*512U;
        if(raw_card.written_sectors) complete_storage(4);
    }
    P[RP_STAGE]=8U; complete_storage(0);
}

void raw_capture_armed(void) { P[RP_ARM]=DWT->CYCCNT; capture_active=1; }
void raw_capture_frame_event(void) { if(!P[RP_FRAME_DONE]) P[RP_FRAME_DONE]=DWT->CYCCNT; }
void raw_capture_data_ready(void)
{
    P[RP_CAMERA_READY]=raw_capture_available();
    P[RP_DMA_BYTES]=RAW10[1]; P[RP_CANARY]=RAW10[7]; P[RP_FRAMES]=TRACE[5];
    P[RP_ERRORS]=TRACE[7]|TRACE[4]; P[RP_FORMAT]=RAW10[8]; P[RP_DATA_TYPE]=RAW10[9];
    P[RP_P0PPCR]=RAW10[2]; P[RP_VC0CFGR1]=RAW10[4]; P[RP_P0FSCR]=RAW10[5];
    P[RP_P0FCTCR]=DCMIPP->P0FCTCR; P[RP_CMSR1]=DCMIPP->CMSR1;
    P[RP_CSI_SR0]=CSI->SR0; P[RP_CSI_SR1]=CSI->SR1;
}
void raw_capture_stopped(void) { P[RP_CAMERA_STOP]=DWT->CYCCNT; }

static int payload_transport(sd_card_t *card,uint32_t lba,const void *data,uint32_t count)
{
#if RAW_WHOLE_IMAGE_PREERASE
    int r=sd_write_blocks_dma_preerase(card,lba,data,count);
#elif RAW_DMA
#if RAW_DMA_SLEEP
    /* First qualification sleeps only after both producer and sensor are done.
     * DWT-based camera STOP deadlines therefore never run across CPU WFI.
     * Remaining SD wall time comes from the independently running SysTick. */
    int r;
    if(raw_capture_frame_validated() && raw_capture_sensor_stopped()) {
        if(!raw_dma_sleep_clocks[6]) {
            const uint32_t ram=RCC_MEMLPENR_AXISRAM1LPEN|RCC_MEMLPENR_AXISRAM2LPEN|
                RCC_MEMLPENR_AXISRAM3LPEN|RCC_MEMLPENR_AXISRAM4LPEN|
                RCC_MEMLPENR_AXISRAM5LPEN|RCC_MEMLPENR_AXISRAM6LPEN;
            const uint32_t rif=RCC_AHB3LPENR_RIFSCLPEN|RCC_AHB3LPENR_RISAFLPEN;
            const uint32_t bus=RCC_BUSLPENR_ACLKNLPEN|RCC_BUSLPENR_ACLKNCLPEN;
            raw_dma_sleep_clocks[0]=RCC->MEMLPENR;
            raw_dma_sleep_clocks[1]=RCC->AHB3LPENR;
            raw_dma_sleep_clocks[2]=RCC->AHB5LPENR;
            raw_dma_sleep_clocks[8]=RCC->BUSLPENR;
            /* Set aliases preserve every unrelated clock. These retain DMA,
             * memory and isolation clocks only during shallow CPU sleep. */
            RCC->MEMLPENSR=RCC_MEMLPENSR_AXISRAM1LPENS|RCC_MEMLPENSR_AXISRAM2LPENS|
                RCC_MEMLPENSR_AXISRAM3LPENS|RCC_MEMLPENSR_AXISRAM4LPENS|
                RCC_MEMLPENSR_AXISRAM5LPENS|RCC_MEMLPENSR_AXISRAM6LPENS;
            RCC->AHB3LPENSR=RCC_AHB3LPENSR_RIFSCLPENS|RCC_AHB3LPENSR_RISAFLPENS;
            RCC->AHB5LPENSR=RCC_AHB5LPENSR_SDMMC2LPENS;
            RCC->BUSLPENSR=RCC_BUSLPENSR_ACLKNLPENS|RCC_BUSLPENSR_ACLKNCLPENS;
            __DSB();
            raw_dma_sleep_clocks[3]=RCC->MEMLPENR;
            raw_dma_sleep_clocks[4]=RCC->AHB3LPENR;
            raw_dma_sleep_clocks[5]=RCC->AHB5LPENR;
            raw_dma_sleep_clocks[9]=RCC->BUSLPENR;
            raw_dma_sleep_clocks[10]=RCC->MISCENR;
            raw_dma_sleep_clocks[11]=RCC->MISCRSTR;
            raw_dma_sleep_clocks[12]=raw_dma_sleep_clocks[13]=0xFFFFFFFFU;
            if((raw_dma_sleep_clocks[10]&RCC_MISCENR_DBGEN) &&
               !(raw_dma_sleep_clocks[11]&RCC_MISCRSTR_DBGRST)) {
                /* Debug sleep emulation retains clocks and would disguise the
                 * real WFI energy. Preserve all ordinary debug-routing bits. */
                raw_dma_sleep_clocks[12]=DBGMCU->CR;
                DBGMCU->CR&=~DBGMCU_CR_DBG_SLEEP;
                __DSB(); raw_dma_sleep_clocks[13]=DBGMCU->CR;
            }
            raw_dma_sleep_clocks[7]=
                (((raw_dma_sleep_clocks[3]&ram)!=ram)?SD_WAIT_RAM_CLOCKS:0U)|
                (((raw_dma_sleep_clocks[4]&rif)!=rif)?SD_WAIT_RIF_CLOCKS:0U)|
                ((!(raw_dma_sleep_clocks[5]&RCC_AHB5LPENR_SDMMC2LPEN))?SD_WAIT_SD_CLOCK:0U)|
                (((raw_dma_sleep_clocks[9]&bus)!=bus)?SD_WAIT_BUS_CLOCKS:0U);
            __DSB(); raw_dma_sleep_clocks[6]=1U;
        }
        /* The driver independently rechecks all masks before launch and WFI. */
        r=sd_write_blocks_dma_wait(card,lba,data,count,&raw_dma_wait);
    } else r=sd_write_blocks_dma(card,lba,data,count);
#else
    int r=sd_write_blocks_dma(card,lba,data,count);
#endif
#else
    int r=sd_write_blocks(card,lba,data,count);
#endif
    /* The slot layer uses the payload callback for its final padded sector,
     * allowing an exact tail-complete marker before its FULL metadata write. */
    if(!r && ((RAW_WHOLE_IMAGE_PREERASE && count==RAW_SLOTS_PAYLOAD_SECTORS) ||
       (raw_slots.written_sectors==RAW_SLOTS_WHOLE_SECTORS && count==1U)))
        (void)phase_gpio_emit(7U);
    return r;
}

#if RAW_MAGIC_FORMAT
#include "magic_runtime.inc"
#endif

void raw_storage_execute(void)
{
#if RAW_MAGIC_FORMAT
    raw_magic_execute();
#else
    if(!raw_card.initialized) init_card();
    raw_capture_poll(); /* safe boundary, outside any SD call */
    P[RP_STAGE]=3U;
    int r; SD_OPERATION(r,raw_slots_open(&raw_slots,&raw_card));
    if(r) complete_storage(0x300U|(uint32_t)r);
    SD_OPERATION(r,raw_slots_find_free(&raw_slots));
    if(r) complete_storage(0x310U|(uint32_t)r);
    P[RP_SCAN_DONE]=DWT->CYCCNT;
    uint32_t began=DWT->CYCCNT;
    while((RAW_WHOLE_IMAGE_PREERASE && !raw_capture_frame_validated()) ||
          (!RAW_LINE_STREAM && raw_capture_available()!=RAW_SLOTS_PAYLOAD_BYTES)) {
        sd_progress();
        if(raw_capture_fault() || (uint32_t)(DWT->CYCCNT-began)>800000000U)
            complete_storage(0x501U);
    }
    raw_slots_metadata_t metadata={.capture_id=(uint64_t)raw_slots.selected_slot+1U,
        .exposure_us=raw_capture_exposure_us(),
        .analog_gain_milli=1000U,.digital_gain_milli=1000U,.orientation=0xFFFFFFFFU,
        .metadata_flags=RAW_SLOTS_META_GAINS_VALID|
            (raw_capture_frame_validated()?RAW_SLOTS_META_EXPOSURE_VALID:0U)};
    if(raw_capture_fault()) complete_storage(0x501U);
    SD_OPERATION(r,raw_slots_begin(&raw_slots,&metadata));
    if(r) complete_storage(0x320U|(uint32_t)r);
    P[RP_SLOT_BEGIN]=DWT->CYCCNT;
    raw_slots.write_payload=payload_transport;
    status_led_set(STATUS_LED_NAND_WRITE); P[RP_STAGE]=5U;
#if RAW_WHOLE_IMAGE_PREERASE
    /* No camera writes remain: validation checked the exact byte count,
     * original32-byte guard, receiver idle and data disable. Pad in place only
     * now; no full-frame copy and no speculative read from an active producer. */
    volatile uint32_t *original_guard=(volatile uint32_t *)(0x34000000U+RAW_SLOTS_PAYLOAD_BYTES);
    volatile uint32_t *pad_guard=(volatile uint32_t *)(0x34000000U+RAW_SLOTS_PADDED_BYTES);
    raw_whole_proof[0]=0x52575031U;raw_whole_proof[1]=1U;
    raw_whole_proof[4]=RAW_SLOTS_PAYLOAD_BYTES;raw_whole_proof[5]=RAW_SLOTS_PADDED_BYTES;
    raw_whole_proof[6]=RAW_SLOTS_PADDED_BYTES-RAW_SLOTS_PAYLOAD_BYTES;
    raw_whole_proof[7]=RAW_SLOTS_PAYLOAD_SECTORS;
    for(uint32_t i=0;i<8U;i++) {
        if(original_guard[i]!=(0xA15A1000U+i)) raw_whole_proof[2]|=1U<<i;
        if(pad_guard[i]!=(0xA15A1000U+i)) raw_whole_proof[3]|=1U<<i;
    }
    if(raw_whole_proof[2] || raw_whole_proof[3] || !raw_capture_frame_validated())
        complete_storage(0x505U);
    volatile uint8_t *pad=(volatile uint8_t *)(0x34000000U+RAW_SLOTS_PAYLOAD_BYTES);
    for(uint32_t i=0;i<RAW_SLOTS_PADDED_BYTES-RAW_SLOTS_PAYLOAD_BYTES;i++) pad[i]=0;
    __DSB();raw_whole_proof[1]=2U;
    P[RP_FIRST_WRITE]=DWT->CYCCNT;(void)phase_gpio_emit(6U);
    uint32_t start=DWT->CYCCNT;
    SD_OPERATION(r,raw_slots_write_padded(&raw_slots,(const void *)0x34000000U));
    volatile uint32_t *row=(volatile uint32_t *)RAW_CHUNK_TRACE_ADDRESS;
    row[0]=start;row[1]=DWT->CYCCNT;row[2]=0;row[3]=RAW_SLOTS_PAYLOAD_SECTORS;
    row[4]=raw_capture_available();row[5]=raw_card.last_ready_r1;
    row[6]=(uint32_t)r;row[7]=raw_card.transfer_cycles;
    __DMB();P[RP_CHUNK_COUNT]=1U;
    if(r) complete_storage(0x330U|(uint32_t)r);
    if(raw_capture_fault()) complete_storage(0x503U);
#else
    uint32_t sectors=0;
    began=DWT->CYCCNT;
    while(sectors<RAW_SLOTS_WHOLE_SECTORS) {
        raw_capture_poll(); /* deferred FRAME/STOP checks only between calls */
        if(raw_capture_fault()) complete_storage(0x503U);
        uint32_t available_bytes=raw_capture_available();
        uint32_t available=available_bytes/512U;
        if(available>RAW_SLOTS_WHOLE_SECTORS) available=RAW_SLOTS_WHOLE_SECTORS;
        uint32_t count=available>sectors?available-sectors:0U;
        if(count>RAW_CHUNK_SECTORS) count=RAW_CHUNK_SECTORS;
        if(!count) {
            if((uint32_t)(DWT->CYCCNT-began)>800000000U) complete_storage(0x504U);
            continue;
        }
        if(!sectors) { P[RP_FIRST_WRITE]=DWT->CYCCNT; (void)phase_gpio_emit(6U); }
        uint32_t at=P[RP_CHUNK_COUNT],start=DWT->CYCCNT;
        SD_OPERATION(r,raw_slots_append(&raw_slots,(const void *)(0x34000000U+sectors*512U),count));
        if(at<RAW_CHUNK_TRACE_CAPACITY) {
            volatile uint32_t *row=(volatile uint32_t *)RAW_CHUNK_TRACE_ADDRESS+at*8U;
            row[0]=start; row[1]=DWT->CYCCNT; row[2]=sectors; row[3]=count;
            row[4]=available_bytes; row[5]=raw_card.last_ready_r1;
            row[6]=(uint32_t)r; row[7]=raw_card.transfer_cycles;
            __DMB(); P[RP_CHUNK_COUNT]=at+1U;
        } else P[RP_CHUNK_OVERFLOW]++;
        if(r) complete_storage(0x330U|(uint32_t)r);
        if(raw_capture_fault()) complete_storage(0x503U);
        sectors+=count;
        began=DWT->CYCCNT;
    }
#endif
    P[RP_PAYLOAD_DONE]=DWT->CYCCNT; P[RP_STAGE]=6U;
    /* A completed image is immutable once camera DMA drains. Sensor STOP can
     * finish concurrently with SD IDMA, but is mandatory before committing and
     * shutting down. Its bounded poll uses no SD API. */
    began=DWT->CYCCNT;
    while(!raw_capture_frame_validated() || !raw_capture_sensor_stopped()) {
        sd_progress();
        if(raw_capture_fault() || (uint32_t)(DWT->CYCCNT-began)>800000000U)
            complete_storage(0x502U);
    }
    capture_active=0;
    raw_slots.metadata.exposure_us=raw_capture_exposure_us();
    raw_slots.metadata.metadata_flags|=RAW_SLOTS_META_EXPOSURE_VALID;
#if RAW_WHOLE_IMAGE_PREERASE
    for(uint32_t i=0;i<8U;i++)
        if(pad_guard[i]!=(0xA15A1000U+i)) raw_whole_proof[3]|=1U<<i;
    if(raw_whole_proof[3]) complete_storage(0x506U);
    raw_whole_proof[1]=3U;__DSB();
    SD_OPERATION(r,raw_slots_commit(&raw_slots));
#else
    SD_OPERATION(r,raw_slots_finish(&raw_slots,(const void *)(0x34000000U+RAW_SLOTS_WHOLE_SECTORS*512U)));
#endif
    if(r) complete_storage(0x340U|(uint32_t)r);
    P[RP_COMMIT_DONE]=DWT->CYCCNT; P[RP_STAGE]=8U;
    (void)phase_gpio_emit(8U);
    complete_storage(0);
#endif
}

int raw_storage_shutdown_ready(void)
{
    return
#if RAW_MAGIC_FORMAT
        raw_magic_proof[0]==0x524D4732U && raw_magic_proof[1]==3U &&
        !raw_magic_proof[2] && !raw_magic_proof[3] &&
        raw_magic_proof[4]==MAGIC_SLOTS_START_MAGIC && raw_magic_proof[5]==MAGIC_SLOTS_END_MAGIC &&
        raw_magic_proof[6]==MAGIC_SLOTS_METADATA_BYTES && raw_magic_proof[7]==3730U &&
        raw_scr.valid && raw_magic_slots.opened && !raw_magic_slots.active &&
        !raw_magic_slots.error && raw_magic_slots.written_sectors==3730U &&
        raw_card.written_sectors==3730U &&
        P[RP_CHUNK_COUNT]==1U && !P[RP_CHUNK_OVERFLOW] &&
#endif
#if RAW_WHOLE_IMAGE_PREERASE
        raw_whole_proof[0]==0x52575031U && raw_whole_proof[1]==3U &&
        !raw_whole_proof[2] && !raw_whole_proof[3] &&
        raw_whole_proof[4]==RAW_SLOTS_PAYLOAD_BYTES && raw_whole_proof[5]==RAW_SLOTS_PADDED_BYTES &&
        raw_whole_proof[6]==160U && raw_whole_proof[7]==RAW_SLOTS_PAYLOAD_SECTORS &&
        P[RP_CHUNK_COUNT]==1U && !P[RP_CHUNK_OVERFLOW] &&
#endif
        P[RP_MAGIC]==RAW_PROOF_MAGIC && P[RP_SCHEMA]==1U &&
        P[RP_TERMINAL]==RAW_PROOF_TERMINAL && P[RP_STATE]==3U &&
        P[RP_OPERATION]==RAW_OP_CAPTURE && !P[RP_RESULT] && P[RP_STAGE]==8U &&
        P[RP_CAMERA_READY]==RAW_SLOTS_PAYLOAD_BYTES && P[RP_CAMERA_STOP] &&
        P[RP_DMA_BYTES]==RAW_SLOTS_PAYLOAD_BYTES &&
        P[RP_FRAMES]==1U && !P[RP_ERRORS] && !P[RP_CANARY] &&
        P[RP_FORMAT]==10U && P[RP_DATA_TYPE]==0x30U &&
        !raw_card.initialized && !raw_card.controller_owned && !raw_card.timer_owned &&
        raw_card.media_idle==1U && !raw_card.error && !raw_card.cleanup_error &&
        raw_card.stage==SD_STAGE_DEINIT && (raw_card.last_ready_r1&0x1F00U)==0x900U &&
        raw_slots.opened && !raw_slots.active && !raw_slots.error &&
        raw_slots.written_sectors==RAW_SLOTS_PAYLOAD_SECTORS &&
        DATA_OFF[0]==0x46534431U && DATA_OFF[2]==4U && !DATA_OFF[15];
}
