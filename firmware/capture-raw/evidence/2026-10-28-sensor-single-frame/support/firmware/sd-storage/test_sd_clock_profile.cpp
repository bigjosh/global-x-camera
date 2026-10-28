/* Actual clock-helper code, modeled RCC effects only; no target access. */
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
#include "stm32n657xx.h"
#define SD_HIGH_SPEED 1
#define SD_REVIEW_PROFILE 1
#include "sd_clock_profile.h"

MockRcc test_rcc;
static bool refuse_enable,refuse_disable,refuse_mux_on,refuse_mux_off,refuse_config,refuse_restore;
static std::vector<const MockReg*> writes;
MockReg::operator uint32_t() const { return value; }
MockReg& MockReg::operator=(uint32_t v)
{
    writes.push_back(this);
    if (this==&test_rcc.DIVENSR) {
        if (!refuse_enable) test_rcc.DIVENR.value|=v;
    } else if (this==&test_rcc.DIVENCR) {
        /* This invariant catches source-off before the mux returns to HCLK. */
        assert(!(test_rcc.CCIPR8.value & RCC_CCIPR8_SDMMC2SEL));
        if (!refuse_disable) test_rcc.DIVENR.value&=~v;
    } else if (this==&test_rcc.CCIPR8) {
        if ((v & RCC_CCIPR8_SDMMC2SEL)==SD_REVIEW_MUX_BITS) {
            assert(test_rcc.DIVENR.value & RCC_DIVENR_IC5EN);
            if (refuse_mux_on) return *this;
        } else if (refuse_mux_off) return *this;
    } else if (this==&test_rcc.IC5CFGR) {
        assert(!(test_rcc.DIVENR.value & RCC_DIVENR_IC5EN));
        if ((v & SD_REVIEW_IC5_MASK)==SD_REVIEW_IC5_BITS ? refuse_config:refuse_restore)
            return *this;
    }
    value=v;
    return *this;
}

static void reset()
{
    test_rcc={};
    std::memset((void*)&sd_review_clock_proof,0,sizeof sd_review_clock_proof);
    refuse_enable=refuse_disable=refuse_mux_on=refuse_mux_off=refuse_config=refuse_restore=false;
    test_rcc.CR.value=test_rcc.SR.value=0x109;
    test_rcc.CFGR1.value=0x33330000; test_rcc.CFGR2.value=0x100000;
    test_rcc.HSICFGR.value=0x9d000000;
    test_rcc.PLL1CFGR1.value=0x404b00; test_rcc.PLL1CFGR3.value=0x49000005;
    test_rcc.IC1CFGR.value=0x20000; test_rcc.IC2CFGR.value=0x30000;
    test_rcc.DIVENR.value=0x423; test_rcc.AHB5ENR.value=0x40002020;
    test_rcc.CCIPR5.value=0xf0f0; test_rcc.CCIPR7.value=0x200;
    writes.clear();
}

static void rejected(unsigned expected)
{
    assert(!sd_review_clock_acquire());
    assert(sd_review_clock_proof.result==expected);
    assert(!sd_review_clock_proof.owned);
    assert(writes.empty());
}

int main()
{
    reset();
    assert(sd_review_clock_acquire());
    assert(sd_review_clock_proof.state==4 && sd_review_clock_proof.kernel_hz==100000000);
    assert(test_rcc.IC5CFGR.value==0xb0000 && test_rcc.DIVENR.value==0x433);
    assert((test_rcc.CCIPR8.value & RCC_CCIPR8_SDMMC2SEL)==0x30);
    assert(sd_review_clock_release());
    assert(test_rcc.IC5CFGR.value==0 && test_rcc.DIVENR.value==0x423 && test_rcc.CCIPR8.value==0);
    assert(sd_review_clock_proof.state==5 && !sd_review_clock_proof.owned);
    const auto n=writes.size(); assert(sd_review_clock_release() && writes.size()==n);

    reset(); test_rcc.IC5CFGR.value=0x10070000; test_rcc.CCIPR8.value=0x12340001;
    assert(sd_review_clock_acquire() && sd_review_clock_release());
    assert(test_rcc.IC5CFGR.value==0x10070000 && test_rcc.CCIPR8.value==0x12340001);

    reset(); test_rcc.SR.value&=~RCC_SR_PLL1RDY; rejected(SD_CLOCK_BAD_PROFILE);
    reset(); test_rcc.CR.value&=~RCC_CR_PLL1ON; rejected(SD_CLOCK_BAD_PROFILE);
    reset(); test_rcc.PLL1CFGR3.value^=1; rejected(SD_CLOCK_BAD_PROFILE);
    reset(); test_rcc.CFGR1.value^=1; rejected(SD_CLOCK_BAD_PROFILE);
    reset(); test_rcc.CFGR2.value^=1; rejected(SD_CLOCK_BAD_PROFILE);
    reset(); test_rcc.IC2CFGR.value^=0x10000; rejected(SD_CLOCK_BAD_PROFILE);
    reset(); test_rcc.HSICFGR.value|=RCC_HSICFGR_HSIDIV; rejected(SD_CLOCK_BAD_PROFILE);
    reset(); test_rcc.DIVENR.value&=~RCC_DIVENR_IC2EN; rejected(SD_CLOCK_BAD_PROFILE);
    reset(); test_rcc.AHB5ENR.value|=RCC_AHB5ENR_SDMMC2EN; rejected(SD_CLOCK_ACTIVE_CONTROLLER);
    reset(); test_rcc.DIVENR.value|=RCC_DIVENR_IC5EN; rejected(SD_CLOCK_BUSY_IC5);
    reset(); test_rcc.CCIPR5.value|=5; rejected(SD_CLOCK_OTHER_CONSUMER);
    reset(); test_rcc.CCIPR7.value|=4; rejected(SD_CLOCK_OTHER_CONSUMER);
    reset(); test_rcc.CCIPR8.value|=3; rejected(SD_CLOCK_OTHER_CONSUMER);
    reset(); test_rcc.CCIPR8.value|=0x10; rejected(SD_CLOCK_OLD_MUX);
    reset(); test_rcc.CCIPR5.value|=(5U<<8); // MCO2=IC15 is not an IC5 consumer.
    assert(sd_review_clock_acquire() && sd_review_clock_release());

    reset(); refuse_config=true;
    assert(!sd_review_clock_acquire() && sd_review_clock_proof.result==SD_CLOCK_CONFIG_READBACK);
    assert(!sd_review_clock_proof.owned && test_rcc.IC5CFGR.value==0);
    reset(); refuse_enable=true;
    assert(!sd_review_clock_acquire() && sd_review_clock_proof.result==SD_CLOCK_ENABLE_TIMEOUT);
    assert(sd_review_clock_proof.enable_polls==SD_REVIEW_CLOCK_POLLS && !sd_review_clock_proof.owned);
    assert(test_rcc.IC5CFGR.value==0 && test_rcc.CCIPR8.value==0);
    reset(); refuse_mux_on=true;
    assert(!sd_review_clock_acquire() && sd_review_clock_proof.result==SD_CLOCK_MUX_READBACK);
    assert(!sd_review_clock_proof.owned && test_rcc.IC5CFGR.value==0 && test_rcc.DIVENR.value==0x423);

    reset(); assert(sd_review_clock_acquire()); writes.clear();
    assert(!sd_review_clock_acquire() && sd_review_clock_proof.owned && writes.empty());
    assert(sd_review_clock_release());
    reset(); assert(sd_review_clock_acquire()); writes.clear();
    test_rcc.AHB5ENR.value|=RCC_AHB5ENR_SDMMC2EN;
    assert(!sd_review_clock_release() && sd_review_clock_proof.owned && writes.empty());
    reset(); assert(sd_review_clock_acquire()); writes.clear(); test_rcc.CCIPR7.value|=4;
    assert(!sd_review_clock_release() && sd_review_clock_proof.owned && writes.empty());
    reset(); assert(sd_review_clock_acquire()); writes.clear(); test_rcc.IC5CFGR.value^=0x10000;
    assert(!sd_review_clock_release() && sd_review_clock_proof.owned && writes.empty());
    reset(); assert(sd_review_clock_acquire()); writes.clear(); test_rcc.SR.value&=~RCC_SR_PLL1RDY;
    assert(!sd_review_clock_release() && sd_review_clock_proof.owned && writes.empty());
    reset(); assert(sd_review_clock_acquire()); writes.clear(); test_rcc.CCIPR8.value=0x10;
    assert(!sd_review_clock_release() && sd_review_clock_proof.owned && writes.empty());
    reset(); assert(sd_review_clock_acquire()); refuse_mux_off=true;
    assert(!sd_review_clock_release() && sd_review_clock_proof.owned);
    assert(test_rcc.DIVENR.value & RCC_DIVENR_IC5EN);
    refuse_mux_off=false; assert(sd_review_clock_release());
    reset(); assert(sd_review_clock_acquire()); refuse_disable=true;
    assert(!sd_review_clock_release() && sd_review_clock_proof.owned);
    assert(sd_review_clock_proof.disable_polls==SD_REVIEW_CLOCK_POLLS);
    assert(test_rcc.CCIPR8.value==0 && test_rcc.IC5CFGR.value==0xb0000);
    refuse_disable=false; assert(sd_review_clock_release());
    reset(); assert(sd_review_clock_acquire()); refuse_restore=true;
    assert(!sd_review_clock_release() && sd_review_clock_proof.owned);
    assert(!(test_rcc.DIVENR.value & RCC_DIVENR_IC5EN));
    refuse_restore=false; assert(sd_review_clock_release());
    std::puts("clock profile ownership and bounded cleanup cases passed");
}
