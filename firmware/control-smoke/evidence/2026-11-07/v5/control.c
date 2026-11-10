/* RAM-only A3/A4/A5 knob diagnostic. No storage, camera, NOR, or sleep code. */
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
 RCC_CCIPR1_SNAPSHOT,PWR_SVMCR3_SNAPSHOT,PA2_IDR,PH2_IDR,PA_MODER,
 PC_MODER,PF_MODER,PH_MODER,PD_MODER,PD_ODR,CFSR,HFSR,IPSR,CCR,
 CONTROL,PRIMASK,FAULTMASK,CFGR1,CFGR2,IC1,PLL1_1,PLL1_2,PLL1_3,
 DWT_START,DWT_DELTA,TERMINAL,ADC_CHANNEL,ADC_BITS,FAIL_STAGE,DIGITAL_FULL_SCALE,
 PWR_SVMCR1_SNAPSHOT,WORDS };
static ADC_HandleTypeDef adc;
static uint32_t last_cycles, fraction_cycles, elapsed_ms;
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
 P[PA2_IDR]=(GPIOA->IDR>>2)&1U;P[PH2_IDR]=(GPIOH->IDR>>2)&1U;
 P[PA_MODER]=GPIOA->MODER;P[PC_MODER]=GPIOC->MODER;
 P[PF_MODER]=GPIOF->MODER;P[PH_MODER]=GPIOH->MODER;
 P[PD_MODER]=GPIOD->MODER;P[PD_ODR]=GPIOD->ODR;
}
static void finish(uint32_t error)
{
 /* Keep the latch on for debugger access; only remove the pot excitation. */
 if(RCC->AHB4ENR&RCC_AHB4ENR_GPIOHEN)GPIOH->BSRR=1U<<18;
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
void control_main(void)
{
 /* First peripheral action retains the new latch if fitted. */
 RCC->AHB4ENSR=RCC_AHB4ENR_GPIODEN;__DSB();
 output(GPIOD,7,1);
 for(unsigned i=0;i<64;i++)P[i]=0;
 P[MAGIC]=0x31434441U;P[VERSION]=1;P[NONCE]=Q[1];P[STATE]=1;
 P[PERIOD_MS]=Q[3];P[MAX_SAMPLES]=Q[2];P[MIN_RAW]=4095;
 P[ADC_CHANNEL]=16;P[ADC_BITS]=12;P[DIGITAL_FULL_SCALE]=4095;
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
 RCC->AHB4ENSR=RCC_AHB4ENR_GPIOAEN|RCC_AHB4ENR_GPIOCEN|RCC_AHB4ENR_GPIOFEN|RCC_AHB4ENR_GPIOHEN|RCC_AHB4ENR_PWREN;
 __DSB();
 /* A4 digital companion must never fight the wiper. */
 GPIOC->MODER&=~(3U<<24);GPIOC->PUPDR&=~(3U<<24);
 GPIOF->MODER|=3U<<6;GPIOF->PUPDR&=~(3U<<6);
 /* Require the selected3.3V bank configuration; do not silently change it. */
 P[PWR_SVMCR1_SNAPSHOT]=PWR->SVMCR1;
 if(PWR->SVMCR1&PWR_SVMCR1_VDDIO4VRSEL)finish(6);
 PWR->SVMCR1|=PWR_SVMCR1_VDDIO4VMEN;__DSB();
 uint32_t supply_start=HAL_GetTick();
 while(!(PWR->SVMCR1&PWR_SVMCR1_VDDIO4RDY)) {
  if(HAL_GetTick()-supply_start>20U){P[PWR_SVMCR1_SNAPSHOT]=PWR->SVMCR1;finish(7);}
 }
 PWR->SVMCR1|=PWR_SVMCR1_VDDIO4SV;__DSB();
 output(GPIOA,2,0);output(GPIOH,2,0);
 /* Monitor board analog1.8V before ASV releases its ADC isolation. */
 PWR->SVMCR3|=PWR_SVMCR3_AVMEN;__DSB();supply_start=HAL_GetTick();
 while(!(PWR->SVMCR3&PWR_SVMCR3_ARDY)) {
  if(HAL_GetTick()-supply_start>20U){P[PWR_SVMCR3_SNAPSHOT]=PWR->SVMCR3;finish(8);}
 }
 PWR->SVMCR3|=PWR_SVMCR3_ASV;__DSB();
 RCC->AHB1RSTSR=RCC_AHB1RSTR_ADC12RST;__DSB();
 RCC->AHB1RSTCR=RCC_AHB1RSTR_ADC12RST;__DSB();
 LL_RCC_SetADCPrescaler(31U);LL_RCC_SetADCClockSource(LL_RCC_ADC_CLKSOURCE_HCLK);
 RCC->AHB1ENSR=RCC_AHB1ENR_ADC12EN;__DSB();P[STATE]=2;
 adc.Instance=ADC1;adc.Init.Resolution=ADC_RESOLUTION_12B;
 adc.Init.ScanConvMode=ADC_SCAN_DISABLE;adc.Init.EOCSelection=ADC_EOC_SINGLE_CONV;
 adc.Init.NbrOfConversion=1;adc.Init.ExternalTrigConv=ADC_SOFTWARE_START;
 adc.Init.ExternalTrigConvEdge=ADC_EXTERNALTRIGCONVEDGE_NONE;
 adc.Init.SamplingMode=ADC_SAMPLING_MODE_NORMAL;
 adc.Init.ConversionDataManagement=ADC_CONVERSIONDATA_DR;
 adc.Init.Overrun=ADC_OVR_DATA_PRESERVED;
 if(HAL_ADC_Init(&adc)!=HAL_OK){snapshot();finish(10);}
 ADC_ChannelConfTypeDef ch={0};ch.Channel=ADC_CHANNEL_16;ch.Rank=ADC_REGULAR_RANK_1;
 ch.SamplingTime=ADC_SAMPLETIME_1499CYCLES_5;ch.SingleDiff=ADC_SINGLE_ENDED;
 ch.OffsetNumber=ADC_OFFSET_NONE;
 if(HAL_ADC_ConfigChannel(&adc,&ch)!=HAL_OK){snapshot();finish(11);}
 P[STATE]=3;
 if(HAL_ADCEx_Calibration_Start(&adc,ADC_SINGLE_ENDED)!=HAL_OK){snapshot();finish(12);}
 output(GPIOH,2,1);uint32_t start=HAL_GetTick();
 while(HAL_GetTick()-start<10U)__NOP();
 P[STATE]=4;
 while(P[SAMPLE_COUNT]<P[MAX_SAMPLES]&&Q[7]!=STOP_MAGIC) {
  start=HAL_GetTick();
  if(HAL_ADC_Start(&adc)!=HAL_OK){snapshot();finish(13);}
  if(HAL_ADC_PollForConversion(&adc,20U)!=HAL_OK){snapshot();finish(14);}
  uint32_t raw=HAL_ADC_GetValue(&adc);
  P[SEQUENCE]++;P[63]=P[SEQUENCE];__DSB();
  P[RAW]=raw;P[SAMPLE_COUNT]++;P[MILLISECONDS]=HAL_GetTick();
  if(raw<P[MIN_RAW])P[MIN_RAW]=raw;
  if(raw>P[MAX_RAW])P[MAX_RAW]=raw;
  snapshot();__DSB();P[63]=P[SEQUENCE]+1U;__DSB();P[SEQUENCE]++;__DSB();
  while(HAL_GetTick()-start<P[PERIOD_MS]&&Q[7]!=STOP_MAGIC)__NOP();
 }
 if(HAL_ADC_Stop(&adc)!=HAL_OK){snapshot();finish(15);}
 snapshot();finish(0);
}
