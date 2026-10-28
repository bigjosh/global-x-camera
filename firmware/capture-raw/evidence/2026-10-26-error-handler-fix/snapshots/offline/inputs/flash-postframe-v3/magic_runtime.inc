/* Included in runtime.c: shares the sole storage owner and terminal guards. */
#if RAW_FLASH
#define MAGIC_LATE __attribute__((section(".raw_late_text"),noinline,noclone))
#else
#define MAGIC_LATE
#endif

_Static_assert(RAW_FRAME_ADDRESS==RAW_SLOT_BUFFER_ADDRESS+MAGIC_SLOTS_IMAGE_OFFSET,
               "front metadata camera address");
_Static_assert(RAW_SLOT_BUFFER_ADDRESS+MAGIC_SLOTS_PADDED_BYTES==
               RAW_FRAME_ADDRESS+MAGIC_SLOTS_IMAGE_BYTES+4U,"overlapping guard geometry");

MAGIC_LATE static int magic_publish(void *context,uint32_t *available)
{
    (void)context;
    raw_capture_poll();
    if(raw_capture_fault()) return 1;
    if(!raw_capture_frame_validated() || !raw_capture_sensor_stopped()) {
        *available=(MAGIC_SLOTS_IMAGE_OFFSET+raw_capture_available())&~511U;
        return 0;
    }
    if(raw_magic_proof[1]<2U) {
        volatile uint32_t *guard=(volatile uint32_t *)(RAW_FRAME_ADDRESS+RAW_SLOTS_PAYLOAD_BYTES);
        volatile uint32_t *end=(volatile uint32_t *)(RAW_SLOT_BUFFER_ADDRESS+MAGIC_SLOTS_PADDED_BYTES);
        for(uint32_t i=0;i<8U;i++) {
            if(guard[i]!=(0xA15A1000U+i)) raw_magic_proof[2]|=1U<<i;
            if(end[i]!=(0xA15A1000U+i+1U)) raw_magic_proof[3]|=1U<<i;
        }
        if(raw_magic_proof[2] || raw_magic_proof[3]) return 2;
        /* Camera has drained and its original guard passed. Only now replace
         * the first guard word with GXRE, the final word of the slot. The
         * remaining overlapping guard words stay outside the stored object. */
        *(volatile uint32_t *)(RAW_SLOT_BUFFER_ADDRESS+MAGIC_SLOTS_TRAILER_OFFSET)=MAGIC_SLOTS_END_MAGIC;
        __DSB(); raw_magic_proof[1]=2U;
        CYCLE_MARK(TRAILER_PUBLISHED);
    }
    *available=MAGIC_SLOTS_PADDED_BYTES;
    return 0;
}

#if RAW_DMA_TAIL_WAIT
#if RAW_FLASH || RAW_STANDBY || !RAW_DMA || !RAW_LINE_STREAM || !RAW_ASYNC_STOP
#error DMA tail wait requires the RAM magic LINE/DMA/asynchronous STOP profile
#endif
volatile uint32_t raw_dma_tail_wait_proof[RAW_DMA_TAIL_WAIT_WORDS];

/* Publication still owns all FRAME/STOP/guard/trailer checks. Only a validated
 * frame missing its final sector may spend this allowance seeking IDMA. Long
 * exposure begins progressive PIO immediately. Expiry is a transport choice,
 * not a camera timeout; errors must still return to outer failure cleanup.
 * The DWT deadline is wrap-safe. One bounded normal publication callback may
 * straddle it; the measured elapsed value includes that callback's time. */
MAGIC_LATE static int magic_dma_tail_wait(uint32_t *available)
{
    volatile uint32_t *const proof=raw_dma_tail_wait_proof;
    for(uint32_t i=0;i<RAW_DMA_TAIL_WAIT_WORDS;i++) proof[i]=0;
    proof[DTW_MAGIC]=RAW_DMA_TAIL_WAIT_MAGIC; proof[DTW_VERSION]=1U;
    proof[DTW_LIMIT]=RAW_DMA_TAIL_WAIT_CYCLES;
    proof[DTW_AVAILABLE_BEFORE]=*available;
    proof[DTW_AVAILABLE_AFTER]=*available;
    proof[DTW_FRAME_BEFORE]=raw_capture_frame_validated();
    proof[DTW_STOPPED_BEFORE]=raw_capture_sensor_stopped();
    const uint32_t start=DWT->CYCCNT;
    proof[DTW_START]=start; proof[DTW_END]=start;
    if(raw_capture_fault()) {
        proof[DTW_OUTCOME]=DTW_FAULT; proof[DTW_RESULT]=1U; return 1;
    }
    if(*available==MAGIC_SLOTS_PADDED_BYTES) {
        proof[DTW_OUTCOME]=DTW_ALREADY_FULL; return 0;
    }
    if(!proof[DTW_FRAME_BEFORE]) {
        proof[DTW_OUTCOME]=DTW_FRAME_PENDING; return 0;
    }
    if(*available<MAGIC_SLOTS_PADDED_BYTES-512U) {
        proof[DTW_OUTCOME]=DTW_PREFIX_SHORT; return 0;
    }
    CYCLE_MARK(DMA_TAIL_WAIT_BEGIN);
    int result=0;
    uint32_t outcome=DTW_TIMEOUT_PIO;
    while((uint32_t)(DWT->CYCCNT-start)<RAW_DMA_TAIL_WAIT_CYCLES) {
        ++proof[DTW_POLLS];
        result=magic_publish(0,available);
        if(result) { outcome=DTW_FAULT; break; }
        if(*available==MAGIC_SLOTS_PADDED_BYTES) {
            outcome=DTW_COMPLETED; break;
        }
    }
    if(!result && raw_capture_fault()) { result=1; outcome=DTW_FAULT; }
    const uint32_t end=DWT->CYCCNT;
    proof[DTW_END]=end; proof[DTW_ELAPSED]=(uint32_t)(end-start);
    proof[DTW_AVAILABLE_AFTER]=*available;
    proof[DTW_RESULT]=(uint32_t)result; proof[DTW_OUTCOME]=outcome;
    CYCLE_MARK(DMA_TAIL_WAIT_DONE);
    return result;
}
#endif

MAGIC_LATE static int magic_transport(sd_card_t *card,uint32_t lba,const void *data,uint32_t count,void *context)
{
    (void)context;
    P[RP_FIRST_WRITE]=DWT->CYCCNT; (void)phase_gpio_emit(6U);
    uint32_t start=DWT->CYCCNT;
    int r=sd_write_blocks_stream_preerase(card,lba,data,count,&raw_stream);
    volatile uint32_t *row=(volatile uint32_t *)RAW_CHUNK_TRACE_ADDRESS;
    row[0]=start;row[1]=DWT->CYCCNT;row[2]=0;row[3]=count;
    row[4]=raw_capture_available();row[5]=card->last_ready_r1;
    row[6]=(uint32_t)r;row[7]=card->transfer_cycles;
    __DMB();P[RP_CHUNK_COUNT]=1U;
    if(!r) (void)phase_gpio_emit(7U);
    return r;
}

MAGIC_LATE static void raw_magic_execute(void) __attribute__((noreturn));
MAGIC_LATE static void raw_magic_execute(void)
{
    if(!raw_card.initialized) init_card();
    raw_capture_poll();
    P[RP_STAGE]=3U;
    CYCLE_MARK(STORAGE_SCR_BEGIN);
    int r; SD_OPERATION(r,sd_read_scr(&raw_card,&raw_scr));
    if(r) complete_storage(0x300U|(uint32_t)r);
    CYCLE_MARK(STORAGE_SCR_DONE);
    r=magic_slots_open(&raw_magic_slots,&raw_card,raw_scr.erased_byte);
    if(r) complete_storage(0x310U|(uint32_t)r);
    CYCLE_MARK(SLOT_SCAN_BEGIN);
    SD_OPERATION(r,magic_slots_find_free(&raw_magic_slots));
    if(r) complete_storage(0x320U|(uint32_t)r);
    CYCLE_MARK(SLOT_SCAN_DONE);
    P[RP_SCAN_DONE]=DWT->CYCCNT;
    raw_magic_proof[0]=0x524D4732U;raw_magic_proof[1]=1U;
    raw_magic_proof[4]=MAGIC_SLOTS_START_MAGIC;raw_magic_proof[5]=MAGIC_SLOTS_END_MAGIC;
    raw_magic_proof[6]=MAGIC_SLOTS_METADATA_BYTES;raw_magic_proof[7]=MAGIC_SLOTS_STRIDE;
    raw_stream.publish=magic_publish;raw_stream.context=0;
    /* Wait only for the first safely published complete sector, not FRAME.
     * Exposure duration can exceed card initialization by a large margin. */
    uint32_t available=0,began=HAL_GetTick();
    CYCLE_MARK(FIRST_SECTOR_WAIT_BEGIN);
    do {
        r=magic_publish(0,&available);
        if(r || HAL_GetTick()-began>3000U) complete_storage(0x501U);
    } while(available<512U);
    CYCLE_MARK(FIRST_SECTOR_WAIT_DONE);
#if RAW_DMA_TAIL_WAIT
    r=magic_dma_tail_wait(&available);
    if(r) complete_storage(0x507U);
#endif
    P[RP_SLOT_BEGIN]=DWT->CYCCNT; P[RP_STAGE]=5U;
    status_led_set(STATUS_LED_NAND_WRITE);
    CYCLE_MARK(SLOT_WRITE_BEGIN);
    SD_OPERATION(r,magic_slots_write(&raw_magic_slots,(const void *)RAW_SLOT_BUFFER_ADDRESS,magic_transport,0));
    if(r) complete_storage(0x330U|(uint32_t)r);
    CYCLE_MARK(SLOT_WRITE_DONE);
    P[RP_PAYLOAD_DONE]=DWT->CYCCNT;P[RP_STAGE]=6U;
    began=HAL_GetTick();
    CYCLE_MARK(FINAL_CAPTURE_WAIT_BEGIN);
    while(!raw_capture_frame_validated() || !raw_capture_sensor_stopped()) {
        sd_progress();
        if(raw_capture_fault() || HAL_GetTick()-began>3000U) complete_storage(0x502U);
    }
    CYCLE_MARK(FINAL_CAPTURE_WAIT_DONE);
    volatile uint32_t *guard=(volatile uint32_t *)(RAW_SLOT_BUFFER_ADDRESS+MAGIC_SLOTS_PADDED_BYTES);
    for(uint32_t i=0;i<8U;i++)
        if(guard[i]!=(0xA15A1000U+i+1U)) raw_magic_proof[3]|=1U<<i;
    if(raw_magic_proof[3] || raw_capture_fault()) complete_storage(0x506U);
    CYCLE_MARK(FINAL_GUARD_DONE);
    capture_active=0;raw_magic_proof[1]=3U;__DSB();
    P[RP_COMMIT_DONE]=DWT->CYCCNT;P[RP_STAGE]=8U;
    CYCLE_MARK(STORAGE_COMPLETE);
    (void)phase_gpio_emit(8U);complete_storage(0);
}
#undef MAGIC_LATE
