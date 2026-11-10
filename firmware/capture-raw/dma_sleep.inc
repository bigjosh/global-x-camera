/* Included only by the reviewed magic-slot sleep profile. Nothing here changes
 * run clocks, IRQ routing, timer frequency, SD launch phase or the recovery guard.
 * The legacy profile remains reproducible, including its original clock proof. */
#if RAW_FLASH
#define DMA_SLEEP_LATE __attribute__((section(".raw_late_text"),noinline,noclone))
#else
#define DMA_SLEEP_LATE
#endif

/* Keep the address-taken callback out of the fixed early image. HAL_GetTick
 * normally inlines there; taking its address would retain an extra early body. */
DMA_SLEEP_LATE static uint32_t raw_dma_milliseconds(void)
{
    return HAL_GetTick();
}

DMA_SLEEP_LATE static int raw_dma_sleep_prepare(void)
{
    volatile uint32_t *const v=raw_dma_sleep_clocks;
    if(v[6]) return v[7]?SD_ERR_WAIT:0;
    const uint32_t ram=RCC_MEMLPENR_AXISRAM1LPEN|RCC_MEMLPENR_AXISRAM2LPEN|
        RCC_MEMLPENR_AXISRAM3LPEN|RCC_MEMLPENR_AXISRAM4LPEN|
        RCC_MEMLPENR_AXISRAM5LPEN|RCC_MEMLPENR_AXISRAM6LPEN;
    const uint32_t rif=RCC_AHB3LPENR_RIFSCLPEN|RCC_AHB3LPENR_RISAFLPEN;
    const uint32_t bus=RCC_BUSLPENR_ACLKNLPEN|RCC_BUSLPENR_ACLKNCLPEN;
    v[0]=RCC->MEMLPENR; v[1]=RCC->AHB3LPENR; v[2]=RCC->AHB5LPENR;
    v[8]=RCC->BUSLPENR; v[14]=RCC->APB4LPENR2;
    /* Set aliases retain unrelated clocks. SRAM includes the frame, stack,
     * vectors, driver and completion proofs. BSEC retention is also required
     * by this profile; its omission in the old failed trial is not proven to
     * have been that trial's cause. */
    RCC->MEMLPENSR=ram;
    RCC->AHB3LPENSR=rif;
    RCC->AHB5LPENSR=RCC_AHB5LPENR_SDMMC2LPEN;
    RCC->BUSLPENSR=bus;
    RCC->APB4LPENSR2=RCC_APB4LPENR2_BSECLPEN;
    __DSB();
    v[3]=RCC->MEMLPENR; v[4]=RCC->AHB3LPENR; v[5]=RCC->AHB5LPENR;
    v[9]=RCC->BUSLPENR; v[15]=RCC->APB4LPENR2;
    v[10]=RCC->MISCENR; v[11]=RCC->MISCRSTR;
    v[12]=v[13]=0xFFFFFFFFU;
    if((v[10]&RCC_MISCENR_DBGEN) && !(v[11]&RCC_MISCRSTR_DBGRST)) {
        v[12]=DBGMCU->CR;
        DBGMCU->CR&=~DBGMCU_CR_DBG_SLEEP;
        __DSB(); v[13]=DBGMCU->CR;
    }
    v[7]=(((v[3]&ram)!=ram)?SD_WAIT_RAM_CLOCKS:0U)|
        (((v[4]&rif)!=rif)?SD_WAIT_RIF_CLOCKS:0U)|
        ((!(v[5]&RCC_AHB5LPENR_SDMMC2LPEN))?SD_WAIT_SD_CLOCK:0U)|
        (((v[9]&bus)!=bus)?SD_WAIT_BUS_CLOCKS:0U)|
        ((!(v[15]&RCC_APB4LPENR2_BSECLPEN) ||
          !(RCC->APB4ENR2&RCC_APB4ENR2_BSECEN))?SD_WAIT_BSEC_CLOCK:0U);
    __DSB(); v[6]=1U;
    /* Driver independently verifies clock, IRQ, SysTick and debug state before
     * launching IDMA and before every WFI. No unsupported state gets to sleep. */
    return v[7]?SD_ERR_WAIT:0;
}
