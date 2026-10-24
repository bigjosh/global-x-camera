/* Offline-built RAM experiment. No SD, NOR, OTP, reset-controller or power API.
 * The caller first qualifies the installed recovery and SRAM initializer.
 * This intentionally resets only the sensor; it is not cold-start timing. */
#include <stdint.h>
#include "stm32n657xx.h"
#include "status_leds.h"
#include "experiment.h"

#define REQUEST ((volatile uint32_t *)0x343FD000U)
#define PROOF ((volatile uint32_t *)0x343FD100U)
#define TRACE ((volatile uint32_t *)0x343F0000U)
#define SENSOR ((volatile uint32_t *)0x343F4000U)
#define RAW10 ((volatile uint32_t *)0x343F6000U)
#define SHUTDOWN ((volatile uint32_t *)0x343F8900U)
#define WIDTH 1120U
#define HEIGHT 1364U
#define BYTES (WIDTH*HEIGHT*(RAW_MODE ? 5U : 8U)/4U)
#define MAGIC 0x52505231U
#define DONE 0x5250444EU
enum {
 P_MAGIC,P_SCHEMA,P_WORDS,P_NONCE,P_MODE,P_PATTERN,P_STATE,P_RESULT,
 P_BYTES,P_FRAME,P_WIDTH,P_HEIGHT,P_DMA_BYTES,P_CANARY,P_FRAMES,P_ERRORS,
 P_FORMAT,P_DT,P_P0PPCR,P_VC0CFGR1,P_P0FSCR,P_P0FCTCR,P_CMSR1,P_CSI_SR0,
 P_CSI_SR1,P_POST_FRAME_BEGIN,P_STOP_END,P_CCR,P_CONTROL,P_IPSR,P_PRIMASK,
 P_FPCCR,P_CPACR,P_SYSTICK,P_RESET_BEGIN,P_RESET_END,P_START_BEGIN,
 P_START_END,P_TERMINAL,P_RESERVED,P_COUNT
};
extern int stage1_sensor_start(void);

__attribute__((noreturn,noinline,used)) static void reject(uint32_t code)
{
    PROOF[P_RESULT]=code; PROOF[P_STATE]=15U;
    __disable_irq(); __DSB(); __ISB();
    PROOF[P_TERMINAL]=DONE; __DSB();
    __asm volatile(".global raw_experiment_reject_park\n"
                   "raw_experiment_reject_park:\n b.n .\n");
    __builtin_unreachable();
}

void raw_experiment_begin(void)
{
    for(unsigned i=0;i<P_COUNT;i++) PROOF[i]=0;
    PROOF[P_MAGIC]=MAGIC; PROOF[P_SCHEMA]=1; PROOF[P_WORDS]=P_COUNT;
    PROOF[P_NONCE]=REQUEST[1]; PROOF[P_MODE]=RAW_MODE; PROOF[P_PATTERN]=RAW_PATTERN;
    PROOF[P_STATE]=1; PROOF[P_RESULT]=0xFFFFFFFFU;
    PROOF[P_BYTES]=BYTES; PROOF[P_FRAME]=0x34000000U;
    PROOF[P_WIDTH]=WIDTH; PROOF[P_HEIGHT]=HEIGHT;
    if(REQUEST[0]!=0x52505131U || !REQUEST[1] || REQUEST[2]!=RAW_MODE ||
       REQUEST[3]!=RAW_PATTERN) reject(1);
    if((SCB->CCR&(SCB_CCR_IC_Msk|SCB_CCR_DC_Msk)) || __get_CONTROL() ||
       __get_IPSR() || __get_PRIMASK()!=1U || __get_FAULTMASK() ||
       (FPU->FPCCR&1U) || (MPU->CTRL&1U)) reject(2);
    if(RCC->CFGR1!=0x33330000U || RCC->CFGR2!=0x00100000U ||
       RCC->PLL1CFGR1!=0x00404B00U || RCC->PLL1CFGR2 ||
       RCC->PLL1CFGR3!=0x49000005U || !(DWT->CTRL&1U)) reject(3);
    if(RCC->AHB5ENR&RCC_AHB5ENR_SDMMC2EN) reject(4);
    const uint32_t clocks=RCC_APB5ENR_CSIEN|RCC_APB5ENR_DCMIPPEN;
    if(RCC->APB5ENR&clocks) reject(5);
    if(((volatile uint32_t *)0x343F5000U)[0]!=0x5231304DU ||
       ((volatile uint32_t *)0x343F5000U)[1]) reject(6);
    status_led_boot_begin(); status_led_proof_init();
    RCC->AHB4ENSR=RCC_AHB4ENSR_GPIODENS|RCC_AHB4ENSR_GPIOEENS;
    (void)RCC->AHB4ENR;
    GPIOD->MODER=(GPIOD->MODER&~3U)|1U;
    GPIOE->MODER=(GPIOE->MODER&~3U)|1U;
    GPIOE->BSRR=1U<<16U; GPIOD->BSRR=1U;
    for(unsigned i=0;i<64;i++) TRACE[i]=0;
    TRACE[0]=0x43545031U; TRACE[16]=RCC->CFGR1; TRACE[17]=RCC->CFGR2;
    TRACE[18]=SCB->CCR; TRACE[19]=BSEC->DBGCR; TRACE[20]=BSEC->AP_UNLOCK;
    /* Exactly the historical explicit-reset path, independently of prior
     * sensor state. It changes no DUT supply or MCU reset state. */
    RCC->AHB4ENSR=RCC_AHB4ENSR_PWRENS|RCC_AHB4ENSR_GPIOOENS;
    (void)RCC->AHB4ENR;
    PWR->SVMCR3|=PWR_SVMCR3_VDDIO2SV; (void)PWR->SVMCR3;
    GPIOO->BSRR=1U<<(5U+16U);
    GPIOO->OTYPER&=~(1U<<5U); GPIOO->PUPDR&=~(3U<<10U);
    GPIOO->OSPEEDR=(GPIOO->OSPEEDR&~(3U<<10U))|(3U<<10U);
    GPIOO->MODER=(GPIOO->MODER&~(3U<<10U))|(1U<<10U);
    PROOF[P_RESET_BEGIN]=DWT->CYCCNT;
    while((uint32_t)(DWT->CYCCNT-PROOF[P_RESET_BEGIN])<40800U) __NOP();
    GPIOO->BSRR=1U<<5U; PROOF[P_RESET_END]=DWT->CYCCNT;
    int result=stage1_sensor_start();
    PROOF[P_START_BEGIN]=SENSOR[4]; PROOF[P_START_END]=SENSOR[5];
    if(result) reject(0x100U|SENSOR[1]);
    PROOF[P_STATE]=2U;
}

__attribute__((noreturn,noinline,used)) void raw_experiment_complete(void)
{
    PROOF[P_DMA_BYTES]=RAW10[1]; PROOF[P_CANARY]=RAW10[7];
    PROOF[P_FRAMES]=TRACE[5]; PROOF[P_ERRORS]=TRACE[7]|TRACE[4];
    PROOF[P_FORMAT]=RAW10[8]; PROOF[P_DT]=RAW10[9];
    PROOF[P_P0PPCR]=RAW10[2]; PROOF[P_VC0CFGR1]=RAW10[4];
    PROOF[P_P0FSCR]=RAW10[5];
    const uint32_t buses=RCC_APB5ENR_CSIEN|RCC_APB5ENR_DCMIPPEN;
    const uint32_t kernels=RCC_DIVENR_IC18EN|RCC_DIVENR_IC17EN;
    const uint32_t resets=RCC_APB5RSTR_CSIRST|RCC_APB5RSTR_DCMIPPRST;
    if((RCC->APB5ENR&buses)!=buses || (RCC->DIVENR&kernels)!=kernels ||
       (RCC->APB5RSTR&resets)) reject(0x201U);
    PROOF[P_P0FCTCR]=DCMIPP->P0FCTCR; PROOF[P_CMSR1]=DCMIPP->CMSR1;
    PROOF[P_CSI_SR0]=CSI->SR0; PROOF[P_CSI_SR1]=CSI->SR1;
    if(PROOF[P_DMA_BYTES]!=BYTES || PROOF[P_CANARY] ||
       PROOF[P_FRAMES]!=1U || PROOF[P_ERRORS] ||
       PROOF[P_FORMAT]!=10U || PROOF[P_DT]!=(RAW_MODE?0x30U:0x2BU) ||
       SHUTDOWN[0]!=0x46534431U || SHUTDOWN[2]!=4U || SHUTDOWN[15] ||
       (DCMIPP->P0FCTCR&DCMIPP_P0FCTCR_CPTREQ) ||
       (DCMIPP->CMSR1&DCMIPP_CMSR1_P0CPTACT) ||
       (DCMIPP->P0FSCR&DCMIPP_P0FSCR_PIPEN) ||
       (CSI->SR0&CSI_SR0_VC0STATEF) || CSI->PCR!=3U) reject(0x202U);
    PROOF[P_POST_FRAME_BEGIN]=((volatile uint32_t *)0x343F8A80U)[16];
    PROOF[P_RESERVED]=RAW10[11]; /* Test-pattern control register readback. */
    PROOF[P_STOP_END]=DWT->CYCCNT;
    status_led_set(STATUS_LED_OFF);
    __disable_irq(); SysTick->CTRL=0; SysTick->VAL=0;
    SCB->ICSR=SCB_ICSR_PENDSTCLR_Msk|SCB_ICSR_PENDSVCLR_Msk;
    if(SCB->CCR&SCB_CCR_DC_Msk) reject(0x203U);
    SCB_DisableICache(); SCB_InvalidateICache(); __DSB(); __ISB();
    PROOF[P_CCR]=SCB->CCR; PROOF[P_CONTROL]=__get_CONTROL();
    PROOF[P_IPSR]=__get_IPSR(); PROOF[P_PRIMASK]=__get_PRIMASK();
    PROOF[P_FPCCR]=FPU->FPCCR; PROOF[P_CPACR]=SCB->CPACR;
    PROOF[P_SYSTICK]=SysTick->CTRL;
    if(PROOF[P_CCR]&0x30000U || PROOF[P_CONTROL] || PROOF[P_IPSR] ||
       PROOF[P_PRIMASK]!=1U || PROOF[P_FPCCR]&1U || PROOF[P_SYSTICK]&3U)
        reject(0x204U);
    PROOF[P_RESULT]=0; PROOF[P_STATE]=3; __DSB();
    PROOF[P_TERMINAL]=DONE; __DSB(); __ISB();
    __asm volatile(".global raw_experiment_park\n"
                   "raw_experiment_park:\n b.n .\n");
    __builtin_unreachable();
}
