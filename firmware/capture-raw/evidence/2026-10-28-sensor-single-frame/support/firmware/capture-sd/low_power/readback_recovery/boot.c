/* RAM-only bridge from verified early recovery. No NOR/card command, reset,
 * sensor access, CSI access, or peripheral power-state transition.
 * raw10_memory_init is copied unchanged from the frozen capture prefix.
 */
#include <stdint.h>
#include "stm32n657xx.h"

#define REQUEST ((volatile uint32_t *)0x341B4000U)
#define PROOF ((volatile uint32_t *)0x341B4100U)
#define MEMORY ((volatile uint32_t *)0x341F5000U)
#define MAGIC 0x52425231U /* RBR1 */
#define DONE 0x5242444EU /* RBDN */
enum {
    P_MAGIC, P_SCHEMA, P_WORDS, P_NONCE, P_RESULT, P_STAGE, P_CCR,
    P_CONTROL, P_IPSR, P_PRIMASK, P_FAULTMASK, P_FPCCR, P_MPU,
    P_CFGR1, P_CFGR2, P_AHB5ENR, P_AHB5RSTR, P_XSPI_SR,
    P_MEMORY_RESULT, P_MEMENR, P_DWT_CTRL, P_DWT_DELTA, P_TERMINAL, P_COUNT
};
extern void raw10_memory_init(void);

static int fail(uint32_t code)
{
    PROOF[P_RESULT]=code;
    __DSB();
    PROOF[P_TERMINAL]=DONE;
    __DSB();
    return (int)code;
}

int readback_boot_main(void)
{
    for(unsigned i=0;i<P_COUNT;i++) PROOF[i]=0;
    PROOF[P_MAGIC]=MAGIC; PROOF[P_SCHEMA]=1; PROOF[P_WORDS]=P_COUNT;
    PROOF[P_NONCE]=REQUEST[1]; PROOF[P_RESULT]=0xFFFFFFFFU;
    PROOF[P_STAGE]=1;
    if(REQUEST[0]!=MAGIC || !REQUEST[1] || REQUEST[2] || REQUEST[3]) return fail(1);
    PROOF[P_CCR]=SCB->CCR; PROOF[P_CONTROL]=__get_CONTROL();
    PROOF[P_IPSR]=__get_IPSR(); PROOF[P_PRIMASK]=__get_PRIMASK();
    PROOF[P_FAULTMASK]=__get_FAULTMASK(); PROOF[P_FPCCR]=FPU->FPCCR;
    PROOF[P_MPU]=MPU->CTRL;
    if(PROOF[P_CCR]&(SCB_CCR_IC_Msk|SCB_CCR_DC_Msk) || PROOF[P_CONTROL] ||
       PROOF[P_IPSR] || PROOF[P_PRIMASK]!=1 || PROOF[P_FAULTMASK] ||
       (PROOF[P_FPCCR]&1U) || (PROOF[P_MPU]&1U)) return fail(2);
    PROOF[P_CFGR1]=RCC->CFGR1; PROOF[P_CFGR2]=RCC->CFGR2;
    if(RCC->CFGR1!=0x33330000U || RCC->CFGR2!=0x00100000U ||
       RCC->PLL1CFGR1!=0x00404B00U || RCC->PLL1CFGR2 ||
       RCC->PLL1CFGR3!=0x49000005U ||
       (RCC->IC1CFGR&(RCC_IC1CFGR_IC1INT|RCC_IC1CFGR_IC1SEL))!=0x20000U ||
       (RCC->IC2CFGR&(RCC_IC2CFGR_IC2INT|RCC_IC2CFGR_IC2SEL))!=0x30000U ||
       !(RCC->DIVENR&RCC_DIVENR_IC2EN)) return fail(3);
    PROOF[P_AHB5ENR]=RCC->AHB5ENR; PROOF[P_AHB5RSTR]=RCC->AHB5RSTR;
    /* Guard before any XSPI read; SD must still be untouched after reset. */
    if((PROOF[P_AHB5ENR]&0x2020U)!=0x2020U ||
       (PROOF[P_AHB5RSTR]&0x2020U) ||
       (PROOF[P_AHB5ENR]&RCC_AHB5ENR_SDMMC2EN)) return fail(4);
    PROOF[P_XSPI_SR]=XSPI1->SR;
    if(PROOF[P_XSPI_SR]&(XSPI_SR_BUSY|XSPI_SR_FLEVEL)) return fail(5);
    /* Prefix initializes LEDs before recovery; require that live dependency. */
    if(!(RCC->AHB4ENR&RCC_AHB4ENR_GPIOGEN) ||
       (GPIOG->MODER&0x00330003U)!=0x00110001U) return fail(6);
    PROOF[P_STAGE]=2;
    raw10_memory_init();
    PROOF[P_MEMORY_RESULT]=MEMORY[1]; PROOF[P_MEMENR]=RCC->MEMENR;
    if(MEMORY[0]!=0x5231304DU || MEMORY[1]) return fail(7);
    CoreDebug->DEMCR|=CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CTRL|=DWT_CTRL_CYCCNTENA_Msk;
    uint32_t before=DWT->CYCCNT;
    for(unsigned i=0;i<32;i++) __NOP();
    PROOF[P_DWT_DELTA]=DWT->CYCCNT-before;
    PROOF[P_DWT_CTRL]=DWT->CTRL;
    if(!(PROOF[P_DWT_CTRL]&1U) || !PROOF[P_DWT_DELTA]) return fail(8);
    PROOF[P_STAGE]=3;
    PROOF[P_RESULT]=0;
    __DSB();
    PROOF[P_TERMINAL]=DONE;
    __DSB();
    return 0;
}
