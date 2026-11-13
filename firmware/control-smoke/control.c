/* RAM-only A0/A1/A2 knob diagnostic with D8 HOLD. No storage/camera/NOR/sleep. */
#include "stm32n6xx_hal.h"
#include "stm32n6xx_ll_rcc.h"

#define Q ((volatile uint32_t *)0x343C1F00U)
#define P ((volatile uint32_t *)0x343C2000U)
#define CPU_HZ 400000000U
#define STOP_MAGIC 0x504F5453U
enum { MAGIC,VERSION,NONCE,STATE,ERROR_CODE,SEQUENCE,SAMPLE_COUNT,RAW,MIN_RAW,
 MAX_RAW,MILLISECONDS,PERIOD_MS,MAX_SAMPLES,HAL_ERROR_CODE,HAL_STATE,
 ADC_CR_SNAPSHOT,ADC_ISR_SNAPSHOT,ADC_CFGR1_SNAPSHOT,ADC_SQR1_SNAPSHOT,
 ADC_SMPR2_SNAPSHOT,ADC_PCSEL_SNAPSHOT,ADC_CALFACT_SNAPSHOT,
 RCC_CCIPR1_SNAPSHOT,PWR_SVMCR3_SNAPSHOT,PF5_IDR,PF6_IDR,PA_MODER,
 PC_MODER,PF_MODER,HOLD_IDR,HOLD_MODER,HOLD_ODR,CFSR,HFSR,IPSR,CCR,
 CONTROL,PRIMASK,FAULTMASK,CFGR1,CFGR2,IC1,PLL1_1,PLL1_2,PLL1_3,
 DWT_START,DWT_DELTA,TERMINAL,ADC_CHANNEL,ADC_BITS,FAIL_STAGE,DIGITAL_FULL_SCALE,
 PWR_SVMCR1_SNAPSHOT,RESERVED53,A0_RAW,A2_RAW,A0_MIN,A0_MAX,A2_MIN,A2_MAX,
 ENDPOINT_VALID,RESERVED61,A1_DIGITAL,WORDS };
static ADC_HandleTypeDef adc;
static uint32_t last_cycles, fraction_cycles, elapsed_ms;
#if defined(CONTROL_INTERNAL_VREF)
static uint32_t vref_settled;
#define V ((volatile uint32_t *)0x343C2200U)
#endif
extern void control_park(void) __attribute__((noreturn));
static void finish(uint32_t error) __attribute__((noreturn));

uint32_t HAL_GetTick(void)
{
 uint32_t now=DWT->CYCCNT,delta=now-last_cycles;last_cycles=now;
 /* Called at least every100ms while running; no DWT-wrap interval is skipped. */
 uint32_t total=fraction_cycles+delta;
 elapsed_ms+=total/(CPU_HZ/1000U);fraction_cycles=total%(CPU_HZ/1000U);
 return elapsed_ms;
}
static void snapshot(void)
{
 P[HAL_ERROR_CODE]=adc.ErrorCode;P[HAL_STATE]=adc.State;
 P[ADC_CR_SNAPSHOT]=ADC1->CR;P[ADC_ISR_SNAPSHOT]=ADC1->ISR;
 P[ADC_CFGR1_SNAPSHOT]=ADC1->CFGR1;P[ADC_SQR1_SNAPSHOT]=ADC1->SQR1;
 P[ADC_SMPR2_SNAPSHOT]=ADC1->SMPR2;P[ADC_PCSEL_SNAPSHOT]=ADC1->PCSEL;
 P[ADC_CALFACT_SNAPSHOT]=ADC1->CALFACT;
 P[RCC_CCIPR1_SNAPSHOT]=RCC->CCIPR1;P[PWR_SVMCR3_SNAPSHOT]=PWR->SVMCR3;
 P[PWR_SVMCR1_SNAPSHOT]=PWR->SVMCR1;
 P[PF5_IDR]=(GPIOF->IDR>>5)&1U;P[PF6_IDR]=(GPIOF->IDR>>6)&1U;
 P[PA_MODER]=GPIOA->MODER;P[PC_MODER]=GPIOC->MODER;
 P[PF_MODER]=GPIOF->MODER;P[HOLD_IDR]=(GPIOD->IDR>>12)&1U;
 P[HOLD_MODER]=GPIOD->MODER;P[HOLD_ODR]=GPIOD->ODR;
}
static void excitation_off(void)
{
 /* A2/PF6 only: D8/PD12 retains the latch; suspect A3/PA2 is untouched. */
 if(RCC->AHB4ENR&RCC_AHB4ENR_GPIOFEN)GPIOF->BSRR=1U<<22;
}
static void finish(uint32_t error)
{
 /* Keep the latch on for debugger access; only remove the pot excitation. */
 excitation_off();
 P[FAIL_STAGE]=P[STATE];P[ERROR_CODE]=error;P[CFSR]=SCB->CFSR;P[HFSR]=SCB->HFSR;P[IPSR]=__get_IPSR();
 P[MILLISECONDS]=elapsed_ms;
 P[STATE]=error?15U:8U;__DSB();P[TERMINAL]=0x454E4F44U;__DSB();
 control_park();
}
void control_fault(void) { finish(0xF000U|__get_IPSR()); }
static void output(GPIO_TypeDef *port,unsigned pin,unsigned high)
{
 port->BSRR=1U<<(pin+(high?0U:16U));
 port->OTYPER&=~(1U<<pin);port->PUPDR&=~(3U<<(2U*pin));
 port->OSPEEDR&=~(3U<<(2U*pin));
 port->MODER=(port->MODER&~(3U<<(2U*pin)))|(1U<<(2U*pin));
 __DSB();
}
static void configure_control_pins(void)
{
 /* A1's raw digital companion must not fight the wiper. */
 GPIOC->MODER&=~(3U<<20);GPIOC->PUPDR&=~(3U<<20);
 /* Only A0/A1/A2 conditioned inputs are Hi-Z. Preserve suspect PA2,
  * its PA12 buffered companion and every unrelated pin's mode/pulls. */
 const uint32_t analog=(3U<<16)|(3U<<18)|(3U<<20);
 GPIOA->MODER|=analog;GPIOA->PUPDR&=~analog;
 /* PF5/PF6 and PD12 are main-VDD pins; VDDIO4 is not involved. */
 output(GPIOF,5,0);output(GPIOF,6,0);
}
static uint32_t sample_channel(uint32_t channel)
{
 /* HAL channel changes require ADC disabled, even with no active conversion. */
 if(HAL_ADC_Stop(&adc)!=HAL_OK){snapshot();finish(15);}
 ADC_ChannelConfTypeDef ch={0};ch.Channel=channel;ch.Rank=ADC_REGULAR_RANK_1;
 ch.SamplingTime=ADC_SAMPLETIME_1499CYCLES_5;ch.SingleDiff=ADC_SINGLE_ENDED;
 ch.OffsetNumber=ADC_OFFSET_NONE;
 if(HAL_ADC_ConfigChannel(&adc,&ch)!=HAL_OK){snapshot();finish(11);}
#if defined(CONTROL_INTERNAL_VREF)
 if(channel==ADC_CHANNEL_VREFINT&&!vref_settled) {
  /* HAL config enables ADC12 common VREFEN. LL specifies12us minimum;
   * this diagnostic waits10ms and never enables the VREFBUF output. */
  uint32_t settle_start=HAL_GetTick();
  while(HAL_GetTick()-settle_start<10U)__NOP();
  vref_settled=1U;
 }
#endif
 if(HAL_ADC_Start(&adc)!=HAL_OK){snapshot();finish(13);}
 if(HAL_ADC_PollForConversion(&adc,20U)!=HAL_OK){snapshot();finish(14);}
 return HAL_ADC_GetValue(&adc);
}
void control_main(void)
{
 /* First peripheral action retains the new latch if fitted. */
 RCC->AHB4ENSR=RCC_AHB4ENR_GPIODEN;__DSB();
 (void)RCC->AHB4ENR;
 output(GPIOD,12,1);
 for(unsigned i=0;i<64;i++)P[i]=0;
#if defined(CONTROL_INTERNAL_VREF)
 for(unsigned i=0;i<16;i++)V[i]=0;
 V[0]=0x46455256U;V[3]=4095U;
#endif
 P[MAGIC]=0x31434441U;P[VERSION]=5;P[NONCE]=Q[1];P[STATE]=1;
 P[PERIOD_MS]=Q[3];P[MAX_SAMPLES]=Q[2];P[MIN_RAW]=4095;
 P[ADC_CHANNEL]=10;P[ADC_BITS]=12;P[DIGITAL_FULL_SCALE]=4095;
 P[A0_MIN]=4095;P[A2_MIN]=4095;
 P[CCR]=SCB->CCR;P[CONTROL]=__get_CONTROL();P[PRIMASK]=__get_PRIMASK();
 P[FAULTMASK]=__get_FAULTMASK();
 if(Q[0]!=0x31544F50U||!Q[1]||!Q[2]||Q[2]>36000U||Q[3]<20U||Q[3]>1000U||Q[4]||Q[5]||Q[6]||Q[7])finish(1);
 if(P[CCR]&0x30000U||P[CONTROL]||P[PRIMASK]!=1U||P[FAULTMASK]||__get_IPSR()||SysTick->CTRL)finish(2);
 P[CFGR1]=RCC->CFGR1;P[CFGR2]=RCC->CFGR2;P[IC1]=RCC->IC1CFGR;
 P[PLL1_1]=RCC->PLL1CFGR1;P[PLL1_2]=RCC->PLL1CFGR2;P[PLL1_3]=RCC->PLL1CFGR3;
 if(P[CFGR1]!=0x33330000U||P[CFGR2]!=0x100000U||P[PLL1_1]!=0x404b00U||P[PLL1_2]||P[PLL1_3]!=0x49000005U||
    (P[IC1]&(RCC_IC1CFGR_IC1SEL|RCC_IC1CFGR_IC1INT))!=0x20000U)finish(3);
 if((RCC->APB5ENR&(RCC_APB5ENR_CSIEN|RCC_APB5ENR_DCMIPPEN))||(RCC->AHB5ENR&RCC_AHB5ENR_SDMMC2EN))finish(4);
 CoreDebug->DEMCR|=CoreDebug_DEMCR_TRCENA_Msk;DWT->CTRL|=1U;
 uint32_t before=DWT->CYCCNT;for(volatile unsigned i=0;i<1000;i++)__NOP();
 P[DWT_START]=before;P[DWT_DELTA]=DWT->CYCCNT-before;if(!P[DWT_DELTA])finish(5);
 last_cycles=DWT->CYCCNT;
 RCC->AHB4ENSR=RCC_AHB4ENR_GPIOAEN|RCC_AHB4ENR_GPIOCEN|RCC_AHB4ENR_GPIOFEN|RCC_AHB4ENR_PWREN;
 __DSB();
 configure_control_pins();
 /* Monitor board analog1.8V before ASV releases its ADC isolation. */
 PWR->SVMCR3|=PWR_SVMCR3_AVMEN;__DSB();uint32_t supply_start=HAL_GetTick();
 while(!(PWR->SVMCR3&PWR_SVMCR3_ARDY)) {
  if(HAL_GetTick()-supply_start>20U){P[PWR_SVMCR3_SNAPSHOT]=PWR->SVMCR3;finish(8);}
 }
 PWR->SVMCR3|=PWR_SVMCR3_ASV;__DSB();
#if defined(CONTROL_VREFBUF_CLOCK)
 /* Match the vendor SystemInit peripheral clock, not its analog output.
  * Board R146 externally feeds VREF+; RM0486 table272 requires ENVR0/HIZ1. */
 RCC->APB4ENSR1=RCC_APB4ENSR1_VREFBUFENS;__DSB();
 if(!(RCC->APB4ENR1&RCC_APB4ENR1_VREFBUFEN))finish(16);
 uint32_t vref_before=VREFBUF->CSR;
 VREFBUF->CSR=(vref_before&~VREFBUF_CSR_ENVR)|VREFBUF_CSR_HIZ;__DSB();
 uint32_t vref_after=VREFBUF->CSR;
 P[RESERVED53]=(vref_before&0xFFFFU)|(vref_after<<16);
 if((vref_after&(VREFBUF_CSR_ENVR|VREFBUF_CSR_HIZ))!=VREFBUF_CSR_HIZ)finish(17);
#endif
 RCC->AHB1RSTSR=RCC_AHB1RSTR_ADC12RST;__DSB();
 RCC->AHB1RSTCR=RCC_AHB1RSTR_ADC12RST;__DSB();
 /* RM0486 section15.3.16: a nonsecure ADC cannot close a secure GPIO's
  * analog switch. Match the official ADC example without changing GPIO
  * security, privilege attributes, or any other peripheral's attribution. */
 volatile uint32_t *security_proof=(volatile uint32_t *)0x343C2300U;
 for(unsigned i=0;i<12;i++)security_proof[i]=0;
 security_proof[0]=0x43455341U;security_proof[11]=Q[1];
 security_proof[8]=RCC->AHB3ENR;
 RCC->AHB3ENSR=RCC_AHB3ENSR_RIFSCENS;__DSB();
 security_proof[9]=RCC->AHB3ENR;
 if(!(security_proof[9]&RCC_AHB3ENR_RIFSCEN))finish(20);
 security_proof[1]=RIFSC->RISC_SECCFGRx[2];
 security_proof[3]=RIFSC->RISC_PRIVCFGRx[2];
 security_proof[5]=GPIOA->SECCFGR;security_proof[6]=GPIOF->SECCFGR;
 security_proof[7]=GPIOC->SECCFGR;
 if((security_proof[5]&0x700U)!=0x700U)finish(21);
 RIFSC->RISC_SECCFGRx[2]|=1U;__DSB();
 security_proof[2]=RIFSC->RISC_SECCFGRx[2];
 security_proof[4]=RIFSC->RISC_PRIVCFGRx[2];
 if(security_proof[2]!=(security_proof[1]|1U)||security_proof[4]!=security_proof[3])finish(22);
 security_proof[10]=1U;__DSB();
#if defined(CONTROL_ADC_HSI8)
 /* Change only ADC mux/divider, leaving HSI and every system clock untouched.
  * HSI64MHz / inherited1,2,4,8 /8 gives1..8MHz, within the ADC limits. */
 volatile uint32_t *clock_proof=(volatile uint32_t *)0x343C2100U;
 clock_proof[0]=RCC->HSICFGR;clock_proof[1]=RCC->SR;
 uint32_t hsi_div=(RCC->HSICFGR&RCC_HSICFGR_HSIDIV)>>RCC_HSICFGR_HSIDIV_Pos;
 clock_proof[2]=(64000000U>>hsi_div)/8U;
 if(!(RCC->SR&RCC_SR_HSIRDY))finish(18);
 LL_RCC_SetADCPrescaler(7U);LL_RCC_SetADCClockSource(LL_RCC_ADC_CLKSOURCE_HSI);__DSB();
 clock_proof[3]=RCC->CCIPR1;
 if((RCC->CCIPR1&(RCC_CCIPR1_ADC12SEL|RCC_CCIPR1_ADCPRE))!=0x750U)finish(19);
#else
 LL_RCC_SetADCPrescaler(31U);LL_RCC_SetADCClockSource(LL_RCC_ADC_CLKSOURCE_HCLK);
#endif
 RCC->AHB1ENSR=RCC_AHB1ENR_ADC12EN;__DSB();P[STATE]=2;
 adc.Instance=ADC1;adc.Init.Resolution=ADC_RESOLUTION_12B;
 adc.Init.ScanConvMode=ADC_SCAN_DISABLE;adc.Init.EOCSelection=ADC_EOC_SINGLE_CONV;
 adc.Init.NbrOfConversion=1;adc.Init.ExternalTrigConv=ADC_SOFTWARE_START;
 adc.Init.ExternalTrigConvEdge=ADC_EXTERNALTRIGCONVEDGE_NONE;
 adc.Init.SamplingMode=ADC_SAMPLING_MODE_NORMAL;
 adc.Init.ConversionDataManagement=ADC_CONVERSIONDATA_DR;
 adc.Init.Overrun=ADC_OVR_DATA_PRESERVED;
 if(HAL_ADC_Init(&adc)!=HAL_OK){snapshot();finish(10);}
 ADC_ChannelConfTypeDef ch={0};ch.Channel=ADC_CHANNEL_10;ch.Rank=ADC_REGULAR_RANK_1;
 ch.SamplingTime=ADC_SAMPLETIME_1499CYCLES_5;ch.SingleDiff=ADC_SINGLE_ENDED;
 ch.OffsetNumber=ADC_OFFSET_NONE;
 if(HAL_ADC_ConfigChannel(&adc,&ch)!=HAL_OK){snapshot();finish(11);}
 P[STATE]=3;
 if(HAL_ADCEx_Calibration_Start(&adc,ADC_SINGLE_ENDED)!=HAL_OK){snapshot();finish(12);}
 output(GPIOF,6,1);uint32_t start=HAL_GetTick();
 while(HAL_GetTick()-start<10U)__NOP();
 P[STATE]=4;
 while(P[SAMPLE_COUNT]<P[MAX_SAMPLES]&&Q[7]!=STOP_MAGIC) {
  start=HAL_GetTick();
#if defined(CONTROL_INTERNAL_VREF)
  uint32_t vref_raw=sample_channel(ADC_CHANNEL_VREFINT);
  uint32_t vref_sqr=ADC1->SQR1;
#endif
  uint32_t low=sample_channel(ADC_CHANNEL_5);
  uint32_t high=sample_channel(ADC_CHANNEL_11);
  uint32_t raw=sample_channel(ADC_CHANNEL_10);
  P[SEQUENCE]++;P[63]=P[SEQUENCE];__DSB();
  P[RAW]=raw;P[SAMPLE_COUNT]++;P[MILLISECONDS]=HAL_GetTick();
  P[A0_RAW]=low;P[A2_RAW]=high;
  if(low<P[A0_MIN])P[A0_MIN]=low;
  if(low>P[A0_MAX])P[A0_MAX]=low;
  if(high<P[A2_MIN])P[A2_MIN]=high;
  if(high>P[A2_MAX])P[A2_MAX]=high;
  P[ENDPOINT_VALID]=1U;
  P[A1_DIGITAL]=(GPIOC->IDR>>10)&1U;
  if(raw<P[MIN_RAW])P[MIN_RAW]=raw;
  if(raw>P[MAX_RAW])P[MAX_RAW]=raw;
  snapshot();__DSB();P[63]=P[SEQUENCE]+1U;__DSB();P[SEQUENCE]++;__DSB();
#if defined(CONTROL_INTERNAL_VREF)
  V[1]++;V[15]=V[1];__DSB();
  V[2]=vref_raw;if(vref_raw<V[3])V[3]=vref_raw;if(vref_raw>V[4])V[4]=vref_raw;
  V[5]=P[SAMPLE_COUNT];V[6]=ADC12_COMMON->CCR;V[7]=ADC1->CFGR2;
  V[8]=ADC1->GCOMP;V[9]=ADC1->OR;V[10]=vref_sqr;
  V[11]=ADC1->CALFACT;V[12]=P[MILLISECONDS];V[13]=Q[1];
  __DSB();V[15]=V[1]+1U;__DSB();V[1]++;__DSB();
#endif
  while(HAL_GetTick()-start<P[PERIOD_MS]&&Q[7]!=STOP_MAGIC)__NOP();
 }
 if(HAL_ADC_Stop(&adc)!=HAL_OK){snapshot();finish(15);}
 snapshot();finish(0);
}
