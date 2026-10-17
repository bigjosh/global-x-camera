/* Offline-built, input-only STROBE latency probe. No timer IRQ or DMA.
 * RM0486 Rev4: 14.10.5 TIMPRE, 15.3.11 AF input, 54.4.7 capture.
 * PA0 AF2=TIM5_CH1; EXTI selection remains active. Root owns execution.
 */
#include "stm32n6xx_hal.h"
#include <stdint.h>

#define TP ((volatile uint32_t *)0x343F7000U)
#define TRACE ((volatile uint32_t *)0x343F0000U)
#define RECORD_WORDS 12U
#define MAX_RECORDS 16U

int timer_probe_init(void)
{
  for(unsigned i=0;i<32U+RECORD_WORDS*MAX_RECORDS;++i) TP[i]=0;
  TP[0]=0x54354943U; TP[1]=1; /* T5IC, incomplete */
  TP[2]=HAL_RCC_GetSysClockFreq(); TP[3]=SystemCoreClock;
  TP[4]=RCC->CFGR1; TP[5]=RCC->CFGR2;
  TP[6]=RCC->IC2CFGR; TP[7]=RCC->DIVENR; TP[8]=RCC->APB1ENR1;
  /* N6 timer clock is sys_bus_ck /2^TIMPRE, NOT APB clock doubling.
   * The matched ROM profile uses TIMPRE=0, sys_bus=300MHz, CPU=400MHz. */
  if(TP[2]!=300000000U || TP[3]!=400000000U ||
     TP[4]!=0x33330000U || TP[5]!=0x00100000U) return -1;
  if(TP[8] & RCC_APB1ENR1_TIM5EN) return -2; /* Refuse another owner. */
  RCC->APB1ENSR1=RCC_APB1ENSR1_TIM5ENS;
  if(!(RCC->APB1ENR1 & RCC_APB1ENR1_TIM5EN)) return -3;
  TP[9]=TIM5->CR1; TP[10]=TIM5->SMCR;
  TP[11]=TIM5->DIER; TP[12]=TIM5->CCER;
  if(TP[9] || TP[10] || TP[11] || TP[12]) return -4;
  if(GPIOA->IDR & 1U) return -5;
  TIM5->CR1=0; TIM5->CR2=0; TIM5->SMCR=0; TIM5->DIER=0;
  TIM5->CCER=0; /* Do not connect AF while channel could be output. */
  TIM5->CCMR1=TIM_CCMR1_CC1S_0; /* IC1 directly maps TI1; filter/prescaler0. */
  TIM5->CCMR2=0; TIM5->TISEL=0; /* TI1 source0 is TIM5_CH1. */
  TIM5->PSC=0; TIM5->ARR=0xFFFFFFFFU; TIM5->CNT=0;
  TIM5->EGR=TIM_EGR_UG; TIM5->SR=0;
  TIM5->CCER=TIM_CCER_CC1E|TIM_CCER_CC1P|TIM_CCER_CC1NP;
  TIM5->CR1=TIM_CR1_CEN;
  /* Input capture is selected before AF2. No output compare/PWM enabled.
   * Direct AFR/MODER update preserves HAL-configured EXTI triggers/mask. */
  GPIOA->AFR[0]=(GPIOA->AFR[0]&~0xFU)|2U;
  GPIOA->MODER=(GPIOA->MODER&~3U)|2U;
  __DSB();
  TP[13]=GPIOA->MODER; TP[14]=GPIOA->AFR[0];
  TP[15]=EXTI->EXTICR[0]; TP[16]=EXTI->RTSR1;
  TP[17]=EXTI->FTSR1; TP[18]=EXTI->IMR1;
  TP[19]=TIM5->CCMR1; TP[20]=TIM5->CCER; TP[21]=TIM5->TISEL;
  TP[22]=TIM5->PSC; TP[23]=TIM5->ARR;
  TP[26]=DWT->CYCCNT; TP[27]=TIM5->CNT; TP[28]=DWT->CYCCNT;
  if((TP[13]&3U)!=2U || (TP[14]&15U)!=2U || TP[19]!=1U ||
     TP[20]!=(TIM_CCER_CC1E|TIM_CCER_CC1P|TIM_CCER_CC1NP) ||
     !(TP[16]&1U) || !(TP[17]&1U) || !(TP[18]&1U)) return -6;
  TP[1]=0;
  return 0;
}

/* Called immediately after the unchanged PE0 event function. The caller
 * reads CNT before event(), so CCR1->PE0 latency is bracketed by the two
 * CNT samples. Reading CCR1 clears CC1IF: preserve SR first. */
void timer_probe_record(uint32_t id,uint32_t before)
{
  uint32_t after=TIM5->CNT;
  uint32_t sr=TIM5->SR;
  uint32_t captured=TIM5->CCR1;
  uint32_t sr_after=TIM5->SR;
  uint32_t cycles=DWT->CYCCNT, pin=GPIOA->IDR;
  uint32_t n=TP[24];
  if(n<MAX_RECORDS) {
    volatile uint32_t *r=TP+32U+n*RECORD_WORDS;
    r[0]=id; r[1]=before; r[2]=after; r[3]=sr; r[4]=captured;
    r[5]=sr_after; r[6]=before-captured; r[7]=after-captured;
    r[8]=cycles; r[9]=pin; r[10]=TRACE[2];
    r[11]=((sr&TIM_SR_CC1IF)?1U:0U) |
          (((sr|sr_after)&TIM_SR_CC1OF)?0U:2U) |
          (((pin&1U)==(id==50U))?4U:0U) |
          ((sr_after&TIM_SR_CC1IF)?0U:8U);
    TP[24]=n+1U;
  } else TP[25]++;
  /* Preserve evidence above before acknowledging any overcapture flag.
   * rc_w0: ones leave other flags unchanged. No timer interrupt is enabled. */
  TIM5->SR=~TIM_SR_CC1OF;
  __DMB();
}

void timer_probe_finish(void)
{
  TP[29]=DWT->CYCCNT; TP[30]=TIM5->CNT; TP[31]=DWT->CYCCNT;
  __DMB();
}
