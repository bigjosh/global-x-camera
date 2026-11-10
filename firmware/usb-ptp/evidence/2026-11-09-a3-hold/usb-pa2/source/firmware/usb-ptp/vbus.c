/* MB1939 C02 CN8 VBUS: R80 140k/R81 10k -> PA11 / ADC2_INP12.
 * Exclusive-use sampler: ADC1/2 must be inactive. No digital threshold or PHY VBUS bit
 * can substitute for this external divider. External VREF+ is board 1.8 V. */
#include "stm32n6xx_hal.h"
#include "stm32n6xx_ll_rcc.h"
volatile uint32_t vbus_proof[16];
int usb_vbus_sample(void)
{
 ADC_HandleTypeDef adc={0};ADC_ChannelConfTypeDef ch={0};int result=-1;
 uint32_t start=HAL_GetTick();
 uint32_t ahb4=RCC->AHB4ENR,ahb3=RCC->AHB3ENR,ahb1=RCC->AHB1ENR;
 RCC->AHB4ENSR=RCC_AHB4ENR_GPIOAEN|RCC_AHB4ENR_PWREN;
 RCC->AHB3ENSR=RCC_AHB3ENR_RIFSCEN;__DSB();
 uint32_t moder=GPIOA->MODER,pupdr=GPIOA->PUPDR,security=RIFSC->RISC_SECCFGRx[2];
 uint32_t supply=PWR->SVMCR3,mux=RCC->CCIPR1;
 vbus_proof[0]=0x31535542;vbus_proof[1]=1;vbus_proof[2]=0;
 if(ahb1&RCC_AHB1ENR_ADC12EN)goto cleanup;
 GPIOA->MODER|=3U<<22;GPIOA->PUPDR&=~(3U<<22);
 RIFSC->RISC_SECCFGRx[2]|=1U;__DSB();
 PWR->SVMCR3|=PWR_SVMCR3_AVMEN;
 while(!(PWR->SVMCR3&PWR_SVMCR3_ARDY)){if(HAL_GetTick()-start>20U)goto cleanup;}
 PWR->SVMCR3|=PWR_SVMCR3_ASV;__DSB();
 RCC->AHB1RSTSR=RCC_AHB1RSTR_ADC12RST;__DSB();RCC->AHB1RSTCR=RCC_AHB1RSTR_ADC12RST;__DSB();
 LL_RCC_SetADCPrescaler(7U);LL_RCC_SetADCClockSource(LL_RCC_ADC_CLKSOURCE_HSI);
 RCC->AHB1ENSR=RCC_AHB1ENR_ADC12EN;__DSB();
 adc.Instance=ADC2;adc.Init.Resolution=ADC_RESOLUTION_12B;adc.Init.ScanConvMode=ADC_SCAN_DISABLE;
 adc.Init.EOCSelection=ADC_EOC_SINGLE_CONV;adc.Init.NbrOfConversion=1;
 adc.Init.ExternalTrigConv=ADC_SOFTWARE_START;adc.Init.ExternalTrigConvEdge=ADC_EXTERNALTRIGCONVEDGE_NONE;
 adc.Init.SamplingMode=ADC_SAMPLING_MODE_NORMAL;adc.Init.ConversionDataManagement=ADC_CONVERSIONDATA_DR;
 adc.Init.Overrun=ADC_OVR_DATA_PRESERVED;
 vbus_proof[1]=2;
 if(HAL_ADC_Init(&adc)!=HAL_OK)goto adc_cleanup;
 ch.Channel=ADC_CHANNEL_12;ch.Rank=ADC_REGULAR_RANK_1;ch.SamplingTime=ADC_SAMPLETIME_1499CYCLES_5;ch.SingleDiff=ADC_SINGLE_ENDED;ch.OffsetNumber=ADC_OFFSET_NONE;
 if(HAL_ADC_ConfigChannel(&adc,&ch)!=HAL_OK||HAL_ADCEx_Calibration_Start(&adc,ADC_SINGLE_ENDED)!=HAL_OK)goto adc_cleanup;
 vbus_proof[1]=3;
 for(unsigned i=0;i<3;i++){
  if(HAL_ADC_Start(&adc)!=HAL_OK||HAL_ADC_PollForConversion(&adc,20U)!=HAL_OK)goto adc_cleanup;
  vbus_proof[3+i]=HAL_ADC_GetValue(&adc);if(HAL_ADC_Stop(&adc)!=HAL_OK)goto adc_cleanup;
 }
 vbus_proof[2]=(vbus_proof[3]+vbus_proof[4]+vbus_proof[5])/3;
 result=vbus_proof[2]>=550U?1:(vbus_proof[2]<200U?0:-1);vbus_proof[1]=4;
adc_cleanup:
 vbus_proof[6]=adc.ErrorCode;vbus_proof[7]=ADC2->ISR;vbus_proof[8]=ADC2->CFGR1;
 HAL_ADC_Stop(&adc);HAL_ADC_DeInit(&adc);RCC->AHB1ENCR=RCC_AHB1ENR_ADC12EN;
cleanup:
 RCC->CCIPR1=(RCC->CCIPR1&~(RCC_CCIPR1_ADC12SEL|RCC_CCIPR1_ADCPRE))|(mux&(RCC_CCIPR1_ADC12SEL|RCC_CCIPR1_ADCPRE));
 GPIOA->MODER=moder;GPIOA->PUPDR=pupdr;RIFSC->RISC_SECCFGRx[2]=security;
 PWR->SVMCR3=(PWR->SVMCR3&~(PWR_SVMCR3_AVMEN|PWR_SVMCR3_ASV))|(supply&(PWR_SVMCR3_AVMEN|PWR_SVMCR3_ASV));
 if(!(ahb3&RCC_AHB3ENR_RIFSCEN))RCC->AHB3ENCR=RCC_AHB3ENR_RIFSCEN;
 RCC->AHB4ENCR=(~ahb4)&(RCC_AHB4ENR_GPIOAEN|RCC_AHB4ENR_PWREN);__DSB();
 vbus_proof[9]=(uint32_t)result;vbus_proof[10]=HAL_GetTick()-start;return result;
}
