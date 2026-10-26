/* Isolated reviewed SDMMC2 clock experiment. Included once by sd_card.c.
 * RM0486 Rev4 Fig59, RCC_IC5CFGR and RCC_CCIPR8: PLL1/(IC5INT+1),
 * SDMMC2SEL=3 selects IC5.  The frozen PLL1 is 1.2 GHz; /12 is 100 MHz.
 * ES0620 Rev5 2.2.22: keep both clocks alive during mux changes and return
 * SDMMC muxes to reset defaults before software reset/ROM execution.
 *
 * Only RCC registers are read; no gated peripheral is probed. IC5's direct
 * mux consumers are MCO1, PER and SDMMC1/2. Reject even a disabled consumer
 * selecting IC5: a later peripheral enable must not inherit our experiment.
 * PER rejection covers its transitive consumers. MCO2's selector5 is IC15.
 * This is exclusive single-owner firmware, not a concurrent RCC allocator.
 */
#ifndef SD_CLOCK_PROFILE_H
#define SD_CLOCK_PROFILE_H
#if !SD_HIGH_SPEED || !SD_REVIEW_PROFILE
#error "The IC5 clock experiment requires SD_HIGH_SPEED and SD_REVIEW_PROFILE"
#endif

#define SD_REVIEW_CLOCK_MAGIC 0x5344434BUL /* SDCK */
#define SD_REVIEW_CLOCK_POLLS 4096UL
#define SD_REVIEW_IC5_BITS (11UL << RCC_IC5CFGR_IC5INT_Pos)
#define SD_REVIEW_IC5_MASK (RCC_IC5CFGR_IC5INT | RCC_IC5CFGR_IC5SEL)
#define SD_REVIEW_MUX_BITS (3UL << RCC_CCIPR8_SDMMC2SEL_Pos)

typedef struct {
    uint32_t magic,version,state,result,owned,stage,enable_polls,disable_polls;
    uint32_t cr,sr,cfgr1,cfgr2,hsicfgr,pll1cfgr1,pll1cfgr2,pll1cfgr3;
    uint32_t ic1cfgr,ic2cfgr,ic5_before,divenr_before;
    uint32_t ccipr5_before,ccipr7_before,ccipr8_before,ahb5_before;
    uint32_t ic5_after,divenr_after,ccipr8_after,ahb5_after;
    uint32_t kernel_hz,cleanup_error,reserved0,reserved1;
} sd_review_clock_proof_t;
volatile sd_review_clock_proof_t sd_review_clock_proof;
_Static_assert(sizeof(sd_review_clock_proof_t)==128U,"SD clock proof ABI");

enum {
    SD_CLOCK_BAD_PROFILE=1,SD_CLOCK_ACTIVE_CONTROLLER=2,
    SD_CLOCK_BUSY_IC5=3,SD_CLOCK_OTHER_CONSUMER=4,SD_CLOCK_OLD_MUX=5,
    SD_CLOCK_CONFIG_READBACK=6,SD_CLOCK_ENABLE_TIMEOUT=7,
    SD_CLOCK_MUX_READBACK=8,SD_CLOCK_NOT_OWNER=9,
    SD_CLOCK_DISABLE_TIMEOUT=10,SD_CLOCK_RESTORE_READBACK=11
};

static void sd_review_clock_snapshot(void)
{
    sd_review_clock_proof.ic5_after=RCC_S->IC5CFGR;
    sd_review_clock_proof.divenr_after=RCC_S->DIVENR;
    sd_review_clock_proof.ccipr8_after=RCC_S->CCIPR8;
    sd_review_clock_proof.ahb5_after=RCC_S->AHB5ENR;
}

static int sd_review_clock_sources(void)
{
    /* Exact source topology used by the frozen 400 MHz CPU/150 MHz HCLK
     * profile; trim/calibration bits in HSICFGR are deliberately ignored. */
    return (RCC_S->CR & (RCC_CR_HSION|RCC_CR_PLL1ON)) ==
               (RCC_CR_HSION|RCC_CR_PLL1ON) &&
           (RCC_S->SR & (RCC_SR_HSIRDY|RCC_SR_PLL1RDY)) ==
               (RCC_SR_HSIRDY|RCC_SR_PLL1RDY) &&
           RCC_S->CFGR1==0x33330000UL && RCC_S->CFGR2==0x00100000UL &&
           !(RCC_S->HSICFGR & RCC_HSICFGR_HSIDIV) &&
           RCC_S->PLL1CFGR1==0x00404B00UL && RCC_S->PLL1CFGR2==0 &&
           RCC_S->PLL1CFGR3==0x49000005UL &&
           (RCC_S->IC1CFGR & (RCC_IC1CFGR_IC1INT|RCC_IC1CFGR_IC1SEL))==0x00020000UL &&
           (RCC_S->IC2CFGR & (RCC_IC2CFGR_IC2INT|RCC_IC2CFGR_IC2SEL))==0x00030000UL &&
           (RCC_S->DIVENR & (RCC_DIVENR_IC1EN|RCC_DIVENR_IC2EN))==
               (RCC_DIVENR_IC1EN|RCC_DIVENR_IC2EN);
}

static int sd_review_clock_consumers(void)
{
    return (RCC_S->CCIPR5 & RCC_CCIPR5_MCO1SEL)!=
               (5UL << RCC_CCIPR5_MCO1SEL_Pos) &&
           (RCC_S->CCIPR7 & RCC_CCIPR7_PERSEL)!=
               (4UL << RCC_CCIPR7_PERSEL_Pos) &&
           (RCC_S->CCIPR8 & RCC_CCIPR8_SDMMC1SEL)!=
               (3UL << RCC_CCIPR8_SDMMC1SEL_Pos);
}

static int sd_review_clock_error(uint32_t error,int cleanup)
{
    if (!sd_review_clock_proof.result) sd_review_clock_proof.result=error;
    if (cleanup) sd_review_clock_proof.cleanup_error=error;
    sd_review_clock_proof.state=sd_review_clock_proof.owned ? 6U:1U;
    sd_review_clock_snapshot();
    return 0;
}

static int sd_review_clock_release(void)
{
    if (!sd_review_clock_proof.owned) return 1;
    sd_review_clock_proof.stage=5;
    if (RCC_S->AHB5ENR & RCC_AHB5ENR_SDMMC2EN)
        return sd_review_clock_error(SD_CLOCK_ACTIVE_CONTROLLER,1);
    if (!sd_review_clock_consumers())
        return sd_review_clock_error(SD_CLOCK_OTHER_CONSUMER,1);
    uint32_t wanted=(sd_review_clock_proof.ic5_before & ~SD_REVIEW_IC5_MASK)|SD_REVIEW_IC5_BITS;
    uint32_t config=RCC_S->IC5CFGR;
    uint32_t enabled=RCC_S->DIVENR & RCC_DIVENR_IC5EN;
    uint32_t mux=RCC_S->CCIPR8 & RCC_CCIPR8_SDMMC2SEL;
    /* An acquire failure can leave the original config, with the gate off.
     * Never overwrite a third party's changed divider or nondefault mux. */
    if ((config!=wanted && (enabled || config!=sd_review_clock_proof.ic5_before)) ||
        (mux!=0 && mux!=SD_REVIEW_MUX_BITS))
        return sd_review_clock_error(SD_CLOCK_NOT_OWNER,1);
    if (mux==SD_REVIEW_MUX_BITS) {
        if (!enabled || !sd_review_clock_sources())
            return sd_review_clock_error(SD_CLOCK_BAD_PROFILE,1);
        RCC_S->CCIPR8=(uint32_t)RCC_S->CCIPR8 & ~RCC_CCIPR8_SDMMC2SEL;
        __DSB();
        if (RCC_S->CCIPR8 & RCC_CCIPR8_SDMMC2SEL)
            return sd_review_clock_error(SD_CLOCK_MUX_READBACK,1);
    }
    sd_review_clock_proof.stage=6;
    if (enabled) {
        RCC_S->DIVENCR=RCC_DIVENCR_IC5ENC;
        __DSB();
        uint32_t i;
        for (i=0;i<SD_REVIEW_CLOCK_POLLS;++i) {
            sd_review_clock_proof.disable_polls=i+1;
            if (!(RCC_S->DIVENR & RCC_DIVENR_IC5EN)) break;
        }
        if (i==SD_REVIEW_CLOCK_POLLS)
            return sd_review_clock_error(SD_CLOCK_DISABLE_TIMEOUT,1);
    }
    RCC_S->IC5CFGR=sd_review_clock_proof.ic5_before;
    __DSB();
    if (RCC_S->IC5CFGR!=sd_review_clock_proof.ic5_before)
        return sd_review_clock_error(SD_CLOCK_RESTORE_READBACK,1);
    sd_review_clock_proof.owned=0;
    sd_review_clock_proof.state=5;
    sd_review_clock_proof.cleanup_error=0;
    sd_review_clock_snapshot();
    return 1;
}

static int sd_review_clock_acquire(void)
{
    if (sd_review_clock_proof.owned)
        return sd_review_clock_error(SD_CLOCK_NOT_OWNER,0);
    volatile uint8_t *bytes=(volatile uint8_t *)&sd_review_clock_proof;
    for (uint32_t i=0;i<sizeof(sd_review_clock_proof);++i) bytes[i]=0;
    sd_review_clock_proof.magic=SD_REVIEW_CLOCK_MAGIC;
    sd_review_clock_proof.version=1;
    sd_review_clock_proof.stage=1;
    sd_review_clock_proof.cr=RCC_S->CR; sd_review_clock_proof.sr=RCC_S->SR;
    sd_review_clock_proof.cfgr1=RCC_S->CFGR1; sd_review_clock_proof.cfgr2=RCC_S->CFGR2;
    sd_review_clock_proof.hsicfgr=RCC_S->HSICFGR;
    sd_review_clock_proof.pll1cfgr1=RCC_S->PLL1CFGR1;
    sd_review_clock_proof.pll1cfgr2=RCC_S->PLL1CFGR2;
    sd_review_clock_proof.pll1cfgr3=RCC_S->PLL1CFGR3;
    sd_review_clock_proof.ic1cfgr=RCC_S->IC1CFGR; sd_review_clock_proof.ic2cfgr=RCC_S->IC2CFGR;
    sd_review_clock_proof.ic5_before=RCC_S->IC5CFGR;
    sd_review_clock_proof.divenr_before=RCC_S->DIVENR;
    sd_review_clock_proof.ccipr5_before=RCC_S->CCIPR5;
    sd_review_clock_proof.ccipr7_before=RCC_S->CCIPR7;
    sd_review_clock_proof.ccipr8_before=RCC_S->CCIPR8;
    sd_review_clock_proof.ahb5_before=RCC_S->AHB5ENR;
    if (!sd_review_clock_sources()) return sd_review_clock_error(SD_CLOCK_BAD_PROFILE,0);
    if (RCC_S->AHB5ENR & RCC_AHB5ENR_SDMMC2EN)
        return sd_review_clock_error(SD_CLOCK_ACTIVE_CONTROLLER,0);
    if (RCC_S->DIVENR & RCC_DIVENR_IC5EN) return sd_review_clock_error(SD_CLOCK_BUSY_IC5,0);
    if (!sd_review_clock_consumers()) return sd_review_clock_error(SD_CLOCK_OTHER_CONSUMER,0);
    if (RCC_S->CCIPR8 & RCC_CCIPR8_SDMMC2SEL) return sd_review_clock_error(SD_CLOCK_OLD_MUX,0);
    sd_review_clock_proof.owned=1;
    sd_review_clock_proof.state=2;
    sd_review_clock_proof.stage=2;
    uint32_t wanted=(sd_review_clock_proof.ic5_before & ~SD_REVIEW_IC5_MASK)|SD_REVIEW_IC5_BITS;
    RCC_S->IC5CFGR=wanted;
    __DSB();
    if (RCC_S->IC5CFGR!=wanted) {
        sd_review_clock_error(SD_CLOCK_CONFIG_READBACK,0);
        (void)sd_review_clock_release();
        return 0;
    }
    RCC_S->DIVENSR=RCC_DIVENSR_IC5ENS;
    __DSB();
    uint32_t i;
    for (i=0;i<SD_REVIEW_CLOCK_POLLS;++i) {
        sd_review_clock_proof.enable_polls=i+1;
        if (RCC_S->DIVENR & RCC_DIVENR_IC5EN) break;
    }
    if (i==SD_REVIEW_CLOCK_POLLS) {
        sd_review_clock_error(SD_CLOCK_ENABLE_TIMEOUT,0);
        (void)sd_review_clock_release();
        return 0;
    }
    sd_review_clock_proof.state=3;
    sd_review_clock_proof.stage=3;
    /* Source-ready recheck immediately before the glitch-free mux update. */
    if (!sd_review_clock_sources() || !sd_review_clock_consumers()) {
        sd_review_clock_error(SD_CLOCK_BAD_PROFILE,0);
        (void)sd_review_clock_release();
        return 0;
    }
    RCC_S->CCIPR8=((uint32_t)RCC_S->CCIPR8 & ~RCC_CCIPR8_SDMMC2SEL)|SD_REVIEW_MUX_BITS;
    __DSB(); __ISB();
    if ((RCC_S->CCIPR8 & RCC_CCIPR8_SDMMC2SEL)!=SD_REVIEW_MUX_BITS) {
        sd_review_clock_error(SD_CLOCK_MUX_READBACK,0);
        (void)sd_review_clock_release();
        return 0;
    }
    sd_review_clock_proof.kernel_hz=100000000UL;
    sd_review_clock_proof.stage=4;
    sd_review_clock_proof.state=4;
    sd_review_clock_snapshot();
    return 1;
}
#endif
