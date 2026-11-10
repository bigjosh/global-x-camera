/* RAM-only, idle-card qualification of the exact capture runtime's 1 ms
 * SysTick/WFI path. This deliberately prevents the pending image write on
 * success as well as failure. No timer/vector/NVIC configuration is changed.
 * The caller has already prepared the reviewed shallow-sleep clocks.
 *
 * DSP1 schema 1, 24 uint32_t words:
 *  0 magic(0x31505344),1 version,2 state,3 result,4 SD_WAIT_* context faults,
 *  5 lifecycle faults,6 awake_tick_begin,7 awake_tick_end,8 awake_cycle_begin,
 *  9 awake_cycle_end,10 sleep_tick_begin,11 sleep_tick_end,12 sleep_cycle_begin,
 * 13 sleep_cycle_end,14 WFI calls,15 WFI returns,16 commands_before,
 * 17 commands_after,18 written_sectors_before(low),19 written_sectors_after(low),
 * 20 CFSR,21 HFSR,22 SD_STA_before,23 SD_STA_after (UINT32_MAX if clock unsafe).
 * States: 1=admission,2=awake timer check,3=sleep,4=success,15=failure.
 * Results: 0=success,1=admission,2=awake timer stalled/overlong,
 * 3=WFI return/tick bounds,4=live context changed.
 * Lifecycle fault bits: 0=wrong owner/callback/depth,1=camera unfinished/fault,
 * 2=card not initialized/owned/idle or prior error,3=SD run clock/reset unsafe,
 * 4=SD command/data/IDMA active,5=commands or writes changed/previous writes,
 * 6=clock preparation missing/failed,7=CPU/DWT/fault-register prerequisite.
 * DWT differences across WFI are active cycles, not elapsed time. Tick deltas
 * are wrap-safe milliseconds. Calls/returns alone do not prove clock gating.
 */
#if RAW_FLASH || RAW_STANDBY || !RAW_DMA_SLEEP || !RAW_MAGIC_FORMAT
#error DMA sleep probe requires the RAM, awake magic-format sleep profile
#endif

volatile uint32_t raw_dma_sleep_probe[24];

static uint32_t raw_dma_sleep_probe_context(sd_card_t *card,sd_dma_wait_t *wait,
                                           uint32_t commands)
{
    uint32_t lifecycle=0U,context=0U;
    const uint32_t ram=RCC_MEMLPENR_AXISRAM1LPEN|RCC_MEMLPENR_AXISRAM2LPEN|
        RCC_MEMLPENR_AXISRAM3LPEN|RCC_MEMLPENR_AXISRAM4LPEN|
        RCC_MEMLPENR_AXISRAM5LPEN|RCC_MEMLPENR_AXISRAM6LPEN;
    const uint32_t rif=RCC_AHB3LPENR_RIFSCLPEN|RCC_AHB3LPENR_RISAFLPEN;
    const uint32_t bus=RCC_BUSLPENR_ACLKNLPEN|RCC_BUSLPENR_ACLKNCLPEN;
    const uint32_t tick=SysTick_CTRL_ENABLE_Msk|SysTick_CTRL_TICKINT_Msk|
        SysTick_CTRL_CLKSOURCE_Msk;
    if(card!=&raw_card || wait!=&raw_dma_wait || !raw_dma_wait.milliseconds ||
       operation!=RAW_OP_CAPTURE || storage_call_depth!=1U) lifecycle|=1U;
    if(!raw_capture_frame_validated() || !raw_capture_sensor_stopped() ||
       raw_capture_fault()) lifecycle|=2U;
    /* These are ownership of the initialized driver, not active transfers. */
    if(!raw_card.initialized || !raw_card.controller_owned || !raw_card.timer_owned ||
       !raw_card.media_idle || raw_card.error || raw_card.cleanup_error) lifecycle|=4U;
    if(!(RCC->AHB5ENR&RCC_AHB5ENR_SDMMC2EN) ||
       (RCC->AHB5RSTR&RCC_AHB5RSTR_SDMMC2RST)) lifecycle|=8U;
    else if((SDMMC2_S->STA&(SDMMC_STA_CPSMACT|SDMMC_STA_DPSMACT)) ||
            SDMMC2_S->IDMACTRL) lifecycle|=16U;
    /* Volatile inspection also retains the otherwise unused no-write stream
     * object for host attribution in this diagnostic's optimized build. */
    if(raw_card.command_count!=commands || raw_card.written_sectors ||
       ((volatile const sd_stream_t *)&raw_stream)->mode!=SD_STREAM_NONE) lifecycle|=32U;
    if(raw_dma_sleep_clocks[6]!=1U || raw_dma_sleep_clocks[7]) lifecycle|=64U;
    if(SystemCoreClock!=400000000U || !(DWT->CTRL&DWT_CTRL_CYCCNTENA_Msk) ||
       SCB->CFSR || SCB->HFSR) lifecycle|=128U;
    if(__get_IPSR()) context|=SD_WAIT_EXCEPTION;
    if(__get_PRIMASK()) context|=SD_WAIT_PRIMASK;
    if(__get_BASEPRI()) context|=SD_WAIT_BASEPRI;
    if(__get_FAULTMASK()) context|=SD_WAIT_FAULTMASK;
    if(SCB->SCR&SCB_SCR_SLEEPDEEP_Msk) context|=SD_WAIT_DEEP_SLEEP;
    if(SCB->SCR&SCB_SCR_SLEEPONEXIT_Msk) context|=SD_WAIT_SLEEP_ON_EXIT;
    if((SysTick->CTRL&tick)!=tick) context|=SD_WAIT_SYSTICK_CTRL;
    if(SysTick->LOAD!=399999U) context|=SD_WAIT_SYSTICK_LOAD;
    if((RCC->MEMLPENR&ram)!=ram) context|=SD_WAIT_RAM_CLOCKS;
    if((RCC->AHB3LPENR&rif)!=rif) context|=SD_WAIT_RIF_CLOCKS;
    if(!(RCC->AHB5LPENR&RCC_AHB5LPENR_SDMMC2LPEN)) context|=SD_WAIT_SD_CLOCK;
    if((RCC->BUSLPENR&bus)!=bus) context|=SD_WAIT_BUS_CLOCKS;
    if(!(RCC->APB4ENR2&RCC_APB4ENR2_BSECEN) ||
       !(RCC->APB4LPENR2&RCC_APB4LPENR2_BSECLPEN)) context|=SD_WAIT_BSEC_CLOCK;
    if(!(RCC->MISCENR&RCC_MISCENR_DBGEN) ||
       (RCC->MISCRSTR&RCC_MISCRSTR_DBGRST)) context|=SD_WAIT_DEBUG_ACCESS;
    else if(DBGMCU->CR&DBGMCU_CR_DBG_SLEEP) context|=SD_WAIT_DEBUG_SLEEP;
    raw_dma_sleep_probe[4]|=context; raw_dma_sleep_probe[5]|=lifecycle;
    return context|lifecycle;
}

static int raw_dma_sleep_probe_run(sd_card_t *card,sd_dma_wait_t *wait)
{
    volatile uint32_t *const v=raw_dma_sleep_probe;
    for(uint32_t i=0U;i<24U;i++) v[i]=0U;
    v[0]=0x31505344U; v[1]=1U; v[2]=1U;
    v[16]=raw_card.command_count; v[18]=(uint32_t)raw_card.written_sectors;
    v[22]=v[23]=0xFFFFFFFFU;
    uint32_t result=0U;
    if(raw_dma_sleep_probe_context(card,wait,v[16])) { result=1U; goto done; }
    v[22]=SDMMC2_S->STA;
    v[2]=2U; v[6]=wait->milliseconds(); v[8]=DWT->CYCCNT;
    uint32_t budget=1000000U;
    while((uint32_t)(wait->milliseconds()-v[6])<3U) {
        if((uint32_t)(DWT->CYCCNT-v[8])>=8000000U || !--budget) {
            result=2U; break;
        }
        __NOP();
    }
    v[7]=wait->milliseconds(); v[9]=DWT->CYCCNT;
    if(result) goto done;
    if((uint32_t)(v[7]-v[6])>4U) { result=2U; goto done; }
    if(raw_dma_sleep_probe_context(card,wait,v[16])) { result=4U; goto done; }
    v[2]=3U; v[10]=wait->milliseconds(); v[12]=DWT->CYCCNT;
    while((uint32_t)(wait->milliseconds()-v[10])<20U) {
        if(v[14]>=1000U) { result=3U; break; }
        if(raw_dma_sleep_probe_context(card,wait,v[16])) { result=4U; break; }
        v[14]++; __DSB(); __WFI(); v[15]++;
    }
    v[11]=wait->milliseconds(); v[13]=DWT->CYCCNT;
    if(!result && (!v[15] || v[14]!=v[15] ||
       (uint32_t)(v[11]-v[10])<20U || (uint32_t)(v[11]-v[10])>21U)) result=3U;
    if(raw_dma_sleep_probe_context(card,wait,v[16]) && !result) result=4U;
done:
    v[17]=raw_card.command_count; v[19]=(uint32_t)raw_card.written_sectors;
    v[20]=SCB->CFSR; v[21]=SCB->HFSR;
    if((RCC->AHB5ENR&RCC_AHB5ENR_SDMMC2EN) &&
       !(RCC->AHB5RSTR&RCC_AHB5RSTR_SDMMC2RST)) v[23]=SDMMC2_S->STA;
    v[3]=result; __DSB(); v[2]=result?15U:4U; __DSB();
    /* Intentional experiment outcome: even a successful sleep proof must
     * unwind through the normal idle cleanup without ever issuing CMD25. */
    return SD_ERR_WAIT;
}
