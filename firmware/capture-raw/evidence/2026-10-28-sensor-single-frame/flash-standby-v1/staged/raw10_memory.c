/* Isolated cold-start RAW10 memory bootstrap, no flash or OTP writes.
 * RM0486 Rev4: SRAM power sequence section10.4; default RISAF rules7.4.3;
 * SRAM3..6 clocks section13.3.1. Parent owns all hardware execution.
 */
#include <stdint.h>
#include "stm32n657xx.h"

#define BOOT ((volatile uint32_t *)0x341F5000U)
#define COPY ((volatile uint32_t *)0x343F5000U)
#define MAGIC 0x5231304DU /* R10M */

__attribute__((noreturn)) void raw10_memory_fault(uint32_t reason)
{
    BOOT[1]=reason;
    BOOT[14]=SCB->CFSR; BOOT[15]=SCB->HFSR;
    BOOT[16]=SCB->BFAR; BOOT[17]=SCB->MMFAR;
    __DSB();
    for(;;) __NOP(); /* Debug stays awake. Do not reset/retry. */
}

void raw10_memory_init(void)
{
    for(unsigned i=0;i<32;++i) BOOT[i]=0;
    BOOT[0]=MAGIC; BOOT[1]=1;
    BOOT[2]=RCC->CFGR1; BOOT[3]=RCC->IC11CFGR;
    BOOT[4]=RCC->DIVENR; BOOT[5]=RCC->MEMENR;
    if(RCC->CFGR1!=0x33330000U || RCC->PLL1CFGR1!=0x00404B00U ||
       RCC->PLL1CFGR2 || RCC->PLL1CFGR3!=0x49000005U)
        raw10_memory_fault(2);
    if(SCB->CCR & SCB_CCR_DC_Msk) raw10_memory_fault(3);
    RCC->AHB2ENSR=RCC_AHB2ENSR_RAMCFGENS;
    RCC->APB4ENSR2=RCC_APB4ENSR2_SYSCFGENS;
    RCC->AHB5ENSR=RCC_AHB5ENSR_CACHEAXIENS;
    (void)RCC->AHB2ENR; (void)RCC->APB4ENR2; (void)RCC->AHB5ENR;
    BOOT[6]=SYSCFG->NPU_ICNCR; BOOT[7]=CACHEAXI->CR1;
    if(SYSCFG->NPU_ICNCR & SYSCFG_NPU_ICNCR_INTERLEAVING_ACTIVE)
        raw10_memory_fault(4);
    if(CACHEAXI->CR1 & CACHEAXI_CR1_EN) raw10_memory_fault(5);
    /* Do not retune an already-active unknown clock or its clients. */
    const uint32_t fields=RCC_IC11CFGR_IC11SEL|RCC_IC11CFGR_IC11INT;
    const uint32_t want=3U<<RCC_IC11CFGR_IC11INT_Pos; /* PLL1 /4 =300MHz */
    if(RCC->DIVENR & RCC_DIVENR_IC11EN) {
        if((RCC->IC11CFGR & fields)!=want) raw10_memory_fault(6);
    } else {
        RCC->IC11CFGR=(RCC->IC11CFGR & ~fields)|want;
        RCC->DIVENSR=RCC_DIVENSR_IC11ENS;
        (void)RCC->DIVENR;
    }
    RAMCFG_TypeDef *const banks[]={RAMCFG_SRAM3_AXI,RAMCFG_SRAM4_AXI,
                                  RAMCFG_SRAM5_AXI,RAMCFG_SRAM6_AXI};
    for(unsigned i=0;i<4;++i) {
        BOOT[8+i]=banks[i]->CR;
        banks[i]->CR &= ~RAMCFG_CR_SRAMSD;
        /* Readback replaces the required40ns delay BEFORE memory clock. */
        if(banks[i]->CR & RAMCFG_CR_SRAMSD) raw10_memory_fault(7+i);
    }
    RCC->MEMENSR=RCC_MEMENSR_AXISRAM3ENS|RCC_MEMENSR_AXISRAM4ENS|
                 RCC_MEMENSR_AXISRAM5ENS|RCC_MEMENSR_AXISRAM6ENS|
                 RCC_MEMENSR_CACHEAXIRAMENS;
    BOOT[12]=RCC->MEMENR; BOOT[13]=RCC->IC11CFGR;
    __DSB();
    /* Sparse, reversible proof of each destination bank. No frame clear. */
    const uint32_t probes[]={0x34200000U,0x34270000U,0x342E0000U,
                             0x34350000U,0x343F0000U};
    for(unsigned i=0;i<5;++i) {
        volatile uint32_t *p=(volatile uint32_t *)probes[i];
        uint32_t saved=*p, value=0xA15A1000U+i;
        *p=value; __DSB();
        BOOT[18+i]=*p;
        if(*p!=value) raw10_memory_fault(11+i);
        *p=saved;
    }
    /* Reserve the parent's post-capture maintenance entry without assuming
     * newly powered SRAM is zero. This is148 bytes of helper and64 bytes of
     * status, both far below the343F diagnostics and above the runtime stack.
     * The helper is loaded/executed by the parent only after frame retrieval. */
    volatile uint32_t *helper=(volatile uint32_t *)0x343C0000U;
    volatile uint32_t *helper_status=(volatile uint32_t *)0x343C0400U;
    for(unsigned i=0;i<37;++i) helper[i]=0;
    for(unsigned i=0;i<16;++i) helper_status[i]=0;
    __DSB();
    for(unsigned i=0;i<37;++i) if(helper[i]) raw10_memory_fault(16);
    for(unsigned i=0;i<16;++i) if(helper_status[i]) raw10_memory_fault(17);
    BOOT[23]=148; BOOT[24]=64;
    BOOT[1]=0;
    for(unsigned i=0;i<32;++i) COPY[i]=BOOT[i];
    __DSB();
}
