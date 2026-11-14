/* One bounded ADC1 sample batch on confirmed battery capture only.
 * Qualified dual-knob pin/security setup; no camera, storage or HOLD writes. */
#include "stm32n6xx_hal.h"
#include "stm32n6xx_ll_rcc.h"
#include "capture_controls.h"
static void output(GPIO_TypeDef *g,unsigned pin,unsigned high) {
 g->BSRR=1U<<(pin+(high?0U:16U));g->OTYPER&=~(1U<<pin);
 g->PUPDR&=~(3U<<(pin*2U));g->OSPEEDR&=~(3U<<(pin*2U));
 g->MODER=(g->MODER&~(3U<<(pin*2U)))|(1U<<(pin*2U));
}
static int sample(ADC_HandleTypeDef *a,uint32_t channel,uint32_t *value) {
 ADC_ChannelConfTypeDef c={0};
 if(HAL_ADC_Stop(a)!=HAL_OK)return 1;
 c.Channel=channel;c.Rank=ADC_REGULAR_RANK_1;c.SamplingTime=ADC_SAMPLETIME_1499CYCLES_5;
 c.SingleDiff=ADC_SINGLE_ENDED;c.OffsetNumber=ADC_OFFSET_NONE;
 if(HAL_ADC_ConfigChannel(a,&c)!=HAL_OK || HAL_ADC_Start(a)!=HAL_OK ||
    HAL_ADC_PollForConversion(a,20U)!=HAL_OK)return 2;
 *value=HAL_ADC_GetValue(a);return 0;
}
void capture_controls_sample(void) {
 volatile capture_controls_t *out=CAPTURE_CONTROLS;capture_controls_t r={0};
 ADC_HandleTypeDef a={0};uint32_t error=1,adc_started=0;
 uint32_t ahb1=RCC->AHB1ENR,ahb3=RCC->AHB3ENR,ahb4=RCC->AHB4ENR;
 const uint32_t clocks=RCC_AHB4ENR_GPIOAEN|RCC_AHB4ENR_GPIOCEN|RCC_AHB4ENR_GPIOFEN|
  RCC_AHB4ENR_GPIOGEN|RCC_AHB4ENR_GPIOHEN|RCC_AHB4ENR_PWREN;
 RCC->AHB4ENSR=clocks;RCC->AHB3ENSR=RCC_AHB3ENR_RIFSCEN;__DSB();
 uint32_t sec=RIFSC->RISC_SECCFGRx[2],priv=RIFSC->RISC_PRIVCFGRx[2];
 uint32_t mux=RCC->CCIPR1,supply=PWR->SVMCR3,bank=PWR->SVMCR1;
 r.magic=CAPTURE_CONTROLS_MAGIC;r.schema=1;r.bytes=sizeof(r);r.state=1;
 r.flags=CC_F_ASA_PROVISIONAL;r.adc_begin=DWT->CYCCNT;
 /* Fail-closed defaults keep both excitation pins LOW from entry onward. */
 output(GPIOF,5,0);output(GPIOF,6,0);output(GPIOC,12,0);
 GPIOC->MODER&=~(3U<<20);GPIOC->PUPDR&=~(3U<<20); /* A1 companion PC10 */
 GPIOH->MODER&=~(3U<<4);GPIOH->PUPDR&=~(3U<<4);   /* A5 companion PH2 */
 GPIOA->MODER|=0x3F0000U;GPIOA->PUPDR&=~0x3F0000U; /* PA8/9/10 conditioned */
 GPIOF->MODER|=3U<<6;GPIOF->PUPDR&=~(3U<<6);       /* PF3 A4 reference */
 GPIOG->MODER|=3U<<30;GPIOG->PUPDR&=~(3U<<30);    /* PG15 A5 wiper */
 __DSB();
 if(ahb1&RCC_AHB1ENR_ADC12EN)goto cleanup;
 error=2;if(bank&PWR_SVMCR1_VDDIO4VRSEL)goto cleanup;
 PWR->SVMCR1|=PWR_SVMCR1_VDDIO4SV;__DSB();
 if(!(PWR->SVMCR1&PWR_SVMCR1_VDDIO4SV))goto cleanup;
 error=3;
 if((GPIOA->SECCFGR&0x700U)!=0x700U || !(GPIOF->SECCFGR&(1U<<3)) ||
    !(GPIOG->SECCFGR&(1U<<15)))goto cleanup;
 RIFSC->RISC_SECCFGRx[2]|=1U;__DSB();
 if(RIFSC->RISC_SECCFGRx[2]!=(sec|1U) || RIFSC->RISC_PRIVCFGRx[2]!=priv)goto cleanup;
 error=4;PWR->SVMCR3|=PWR_SVMCR3_AVMEN;__DSB();uint32_t start=HAL_GetTick();
 while(!(PWR->SVMCR3&PWR_SVMCR3_ARDY)){if(HAL_GetTick()-start>20U)goto cleanup;}
 PWR->SVMCR3|=PWR_SVMCR3_ASV;__DSB();
 RCC->AHB1RSTSR=RCC_AHB1RSTR_ADC12RST;__DSB();RCC->AHB1RSTCR=RCC_AHB1RSTR_ADC12RST;__DSB();
 LL_RCC_SetADCPrescaler(31U);LL_RCC_SetADCClockSource(LL_RCC_ADC_CLKSOURCE_HCLK);
 RCC->AHB1ENSR=RCC_AHB1ENR_ADC12EN;__DSB();adc_started=1;
 a.Instance=ADC1;a.Init.Resolution=ADC_RESOLUTION_12B;a.Init.ScanConvMode=ADC_SCAN_DISABLE;
 a.Init.EOCSelection=ADC_EOC_SINGLE_CONV;a.Init.NbrOfConversion=1;
 a.Init.ExternalTrigConv=ADC_SOFTWARE_START;a.Init.ExternalTrigConvEdge=ADC_EXTERNALTRIGCONVEDGE_NONE;
 a.Init.SamplingMode=ADC_SAMPLING_MODE_NORMAL;a.Init.ConversionDataManagement=ADC_CONVERSIONDATA_DR;
 a.Init.Overrun=ADC_OVR_DATA_PRESERVED;
 error=5;if(HAL_ADC_Init(&a)!=HAL_OK || HAL_ADCEx_Calibration_Start(&a,ADC_SINGLE_ENDED)!=HAL_OK)goto cleanup;
 output(GPIOF,6,1);output(GPIOC,12,1);__DSB();
 start=HAL_GetTick();while(HAL_GetTick()-start<10U)__NOP();
 error=6;
 if(sample(&a,ADC_CHANNEL_5,&r.adc_low) || sample(&a,ADC_CHANNEL_11,&r.exposure_high) ||
    sample(&a,ADC_CHANNEL_16,&r.asa_high) || sample(&a,ADC_CHANNEL_10,&r.exposure_raw) ||
    sample(&a,ADC_CHANNEL_7,&r.asa_raw))goto cleanup;
 error=7;if(capture_controls_map(&r))goto cleanup;
 error=0;r.flags|=CC_F_ADC_VALID;
cleanup:
 /* No failure path may retain pot excitation or touch PD12/PE6/retired PA2. */
 GPIOF->BSRR=1U<<22;GPIOC->BSRR=1U<<28;__DSB();
 r.flags|=CC_F_EXCITATION_OFF;
 if(adc_started){
  int stop=HAL_ADC_Stop(&a),deinit=HAL_ADC_DeInit(&a);
  if(!error && (stop!=HAL_OK || deinit!=HAL_OK))error=8;
  RCC->AHB1ENCR=RCC_AHB1ENR_ADC12EN;
 }
 RCC->CCIPR1=(RCC->CCIPR1&~(RCC_CCIPR1_ADC12SEL|RCC_CCIPR1_ADCPRE))|
  (mux&(RCC_CCIPR1_ADC12SEL|RCC_CCIPR1_ADCPRE));
 RIFSC->RISC_SECCFGRx[2]=sec;
 PWR->SVMCR3=(PWR->SVMCR3&~(PWR_SVMCR3_AVMEN|PWR_SVMCR3_ASV))|(supply&(PWR_SVMCR3_AVMEN|PWR_SVMCR3_ASV));
 PWR->SVMCR1=(PWR->SVMCR1&~PWR_SVMCR1_VDDIO4SV)|(bank&PWR_SVMCR1_VDDIO4SV);
 if(!(ahb3&RCC_AHB3ENR_RIFSCEN))RCC->AHB3ENCR=RCC_AHB3ENR_RIFSCEN;
 RCC->AHB4ENCR=(~ahb4)&clocks;__DSB();
 if(error)r.flags&=~CC_F_ADC_VALID;
 r.error=error;r.state=error?CC_FAILED:CC_ADC_READY;r.adc_end=DWT->CYCCNT;
 r.crc32=capture_controls_crc(&r);
 const uint32_t *src=(const uint32_t *)&r;volatile uint32_t *dst=(volatile uint32_t *)out;
 for(unsigned i=0;i<32;i++)dst[i]=src[i];__DSB();
}
