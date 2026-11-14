/* Exposure and analog-gain knobs for the battery capture path.
 *
 * The selector calls knob_apply() once per boot, after VBUS is found absent
 * and before the unchanged capture prefix configures the sensor. The two
 * readings are applied by editing the RAM copy of that prefix in two places:
 * the manual-exposure register block (analog gain and exposure lines) and the
 * frame-length constant. The flash contents of the capture code are the
 * reviewed bytes; only this boot's RAM copy carries the knob settings.
 * Any failure leaves the prefix untouched, which gives the fixed settings
 * used before the knobs existed (1428 lines, gain 1x, frame 4336 lines).
 *
 * Wiring, NUCLEO-N657X0-Q MB1940 C02 (docs/prototype/nucleo-assembly-guide.md):
 *   Exposure knob: track from A0/PF5 (driven LOW) to A2/PF6 (driven HIGH),
 *     wiper on A1 -> board divider and buffer -> PA9 / ADC1 input 10.
 *   Gain knob: track from A4/PC12 (driven HIGH) to GND,
 *     wiper on A5 -> board divider and buffer -> PG15 / ADC1 input 7.
 * PC12 belongs to the VDDIO4 pin bank, which drives only while marked valid.
 * The raw header pins sharing each wiper (PC10 with A1, PH2 with A5) stay
 * inputs without pulls. The buffered companions of the driven pins (PA8 for
 * A0, PA10 for A2, PF3 for A4) stay analog. Excitation lasts only for the
 * reading; every register this function changes is put back before it returns.
 *
 * Exclusive use, like vbus.c: ADC1/2 must be inactive on entry.
 */
#include "stm32n6xx_hal.h"
#include "stm32n6xx_ll_rcc.h"
#include "knob_map.h"
#include "knob_config.h"

/* Record for bench inspection; the selector publishes its address. */
enum { K_MAGIC, K_STATE, K_RESULT, K_EXPOSURE_FIRST, K_GAIN_FIRST, K_EXPOSURE_CODE, K_GAIN_CODE,
       K_LINES, K_FRAME, K_GAIN, K_MANUAL_ADDRESS, K_FRAME_ADDRESS, K_FRAME_WORD, K_ADC_ERROR,
       K_ADC_ISR, K_CALFACT, K_SVMCR1_BEFORE, K_SVMCR1_DURING, K_GPIOA_SECURE, K_GPIOG_SECURE,
       K_SETTLE_CYCLES, K_TOTAL_CYCLES, K_WORDS=32 };
volatile uint32_t knob_proof[K_WORDS];

/* Result codes; zero means the knob settings were applied. */
enum { KNOB_APPLIED=0, KNOB_ADC_IN_USE=1, KNOB_BANK_1V8=2, KNOB_SUPPLY=3, KNOB_ADC_INIT=4,
       KNOB_ADC_SETUP=5, KNOB_CONVERSION=6, KNOB_PREFIX_DIFFERS=7, KNOB_READBACK=8 };

/* Excitation must be stable at the buffered ADC inputs before sampling.
 * The divider has no capacitor and the buffer settles in tens of
 * microseconds; one millisecond at the inherited 400 MHz clock is ample. */
#define SETTLE_CYCLES 400000U

#define A_ANALOG ((3U<<16)|(3U<<18)|(3U<<20))   /* PA8, PA9, PA10 */
#define G_ANALOG (3U<<30)                       /* PG15 */
#define H_INPUT (3U<<4)                         /* PH2 */

/* Pin registers this function changes, saved on entry and written back whole
 * on exit, mode first so a driven pin stops driving before anything else.
 * Nothing else runs in between: the selector is single-threaded. */
static volatile uint32_t *const pin_registers[]={
 &GPIOF->MODER,&GPIOF->PUPDR,&GPIOF->OTYPER,&GPIOF->OSPEEDR,&GPIOF->ODR,
 &GPIOC->MODER,&GPIOC->PUPDR,&GPIOC->OTYPER,&GPIOC->OSPEEDR,&GPIOC->ODR,
 &GPIOA->MODER,&GPIOA->PUPDR,&GPIOG->MODER,&GPIOG->PUPDR,&GPIOH->MODER,&GPIOH->PUPDR};
#define PIN_REGISTERS (sizeof pin_registers/sizeof pin_registers[0])

static void drive(GPIO_TypeDef *port,unsigned pin,unsigned high)
{
 port->BSRR=1U<<(pin+(high?0U:16U));
 port->OTYPER&=~(1U<<pin);port->PUPDR&=~(3U<<(2U*pin));port->OSPEEDR&=~(3U<<(2U*pin));
 port->MODER=(port->MODER&~(3U<<(2U*pin)))|(1U<<(2U*pin));
 __DSB();
}

static int convert(ADC_HandleTypeDef *adc,uint32_t channel,volatile uint32_t *to)
{
 /* The channel may change only while the converter is stopped. */
 ADC_ChannelConfTypeDef ch={0};
 ch.Channel=channel;ch.Rank=ADC_REGULAR_RANK_1;ch.SamplingTime=ADC_SAMPLETIME_1499CYCLES_5;
 ch.SingleDiff=ADC_SINGLE_ENDED;ch.OffsetNumber=ADC_OFFSET_NONE;
 if(HAL_ADC_ConfigChannel(adc,&ch)!=HAL_OK||HAL_ADC_Start(adc)!=HAL_OK||
    HAL_ADC_PollForConversion(adc,20U)!=HAL_OK)return 0;
 *to=HAL_ADC_GetValue(adc);
 return HAL_ADC_Stop(adc)==HAL_OK;
}

/* Write the setting into the capture prefix. Returns a result code. */
static uint32_t patch(struct knob_setting setting)
{
 volatile uint8_t *manual=(volatile uint8_t *)KNOB_MANUAL_ADDRESS;
 volatile uint8_t *frame=(volatile uint8_t *)KNOB_FRAME_ADDRESS;
 const uint8_t expected[12]={2,0,KNOB_DEFAULT_LINES&255U,KNOB_DEFAULT_LINES>>8,0,1,0,1,0,1,0,1};
 uint32_t before=knob_movw_r1(KNOB_DEFAULT_FRAME),after=knob_movw_r1(setting.frame);
 /* Refuse to edit anything but the exact bytes this build was made for. */
 for(unsigned i=0;i<12;i++)if(manual[i]!=expected[i])return KNOB_PREFIX_DIFFERS;
 for(unsigned i=0;i<4;i++)if(frame[i]!=(uint8_t)(before>>(8U*i)))return KNOB_PREFIX_DIFFERS;
 manual[1]=setting.gain;manual[2]=(uint8_t)setting.lines;manual[3]=(uint8_t)(setting.lines>>8);
 for(unsigned i=0;i<4;i++)frame[i]=(uint8_t)(after>>(8U*i));
 __DSB();__ISB();
 knob_proof[K_FRAME_WORD]=after;
 unsigned good=manual[1]==setting.gain&&manual[2]==(uint8_t)setting.lines&&
               manual[3]==(uint8_t)(setting.lines>>8);
 for(unsigned i=0;i<4;i++)if(frame[i]!=(uint8_t)(after>>(8U*i)))good=0;
 if(good)return KNOB_APPLIED;
 /* Never leave a half-written setting: put the fixed defaults back. */
 for(unsigned i=0;i<12;i++)manual[i]=expected[i];
 for(unsigned i=0;i<4;i++)frame[i]=(uint8_t)(before>>(8U*i));
 __DSB();__ISB();
 return KNOB_READBACK;
}

uint32_t knob_apply(void)
{
 ADC_HandleTypeDef adc={0};uint32_t result=KNOB_ADC_IN_USE,began=DWT->CYCCNT,start=HAL_GetTick();
 uint32_t ahb4=RCC->AHB4ENR,ahb3=RCC->AHB3ENR,ahb1=RCC->AHB1ENR;
 const uint32_t clocks=RCC_AHB4ENR_GPIOAEN|RCC_AHB4ENR_GPIOCEN|RCC_AHB4ENR_GPIOFEN|
                       RCC_AHB4ENR_GPIOGEN|RCC_AHB4ENR_GPIOHEN|RCC_AHB4ENR_PWREN;
 RCC->AHB4ENSR=clocks;RCC->AHB3ENSR=RCC_AHB3ENR_RIFSCEN;__DSB();
 uint32_t pins[PIN_REGISTERS];
 for(unsigned i=0;i<PIN_REGISTERS;i++)pins[i]=*pin_registers[i];
 uint32_t security=RIFSC->RISC_SECCFGRx[2],supply=PWR->SVMCR3,bank=PWR->SVMCR1,mux=RCC->CCIPR1;
 for(unsigned i=0;i<K_WORDS;i++)knob_proof[i]=0;
 knob_proof[K_MAGIC]=0x31424E4BU; /* KNB1 */
 knob_proof[K_STATE]=1;knob_proof[K_RESULT]=0xFFFFFFFFU;
 knob_proof[K_MANUAL_ADDRESS]=KNOB_MANUAL_ADDRESS;knob_proof[K_FRAME_ADDRESS]=KNOB_FRAME_ADDRESS;
 knob_proof[K_LINES]=KNOB_DEFAULT_LINES;knob_proof[K_FRAME]=KNOB_DEFAULT_FRAME;
 knob_proof[K_SVMCR1_BEFORE]=bank;
 knob_proof[K_GPIOA_SECURE]=GPIOA->SECCFGR;knob_proof[K_GPIOG_SECURE]=GPIOG->SECCFGR;
 if(ahb1&RCC_AHB1ENR_ADC12EN)goto cleanup;
 /* PC12 would drive 3.3 V logic levels into a bank configured for 1.8 V. */
 result=KNOB_BANK_1V8;
 if(bank&PWR_SVMCR1_VDDIO4VRSEL)goto cleanup;

 /* Conditioned inputs and the raw pins that share the two wipers. */
 GPIOA->MODER|=A_ANALOG;GPIOA->PUPDR&=~A_ANALOG;
 GPIOG->MODER|=G_ANALOG;GPIOG->PUPDR&=~G_ANALOG;
 GPIOF->MODER|=3U<<6;GPIOF->PUPDR&=~(3U<<6);
 GPIOC->MODER&=~(3U<<20);GPIOC->PUPDR&=~(3U<<20);
 GPIOH->MODER&=~H_INPUT;GPIOH->PUPDR&=~H_INPUT;
 /* Excite both tracks. */
 drive(GPIOF,5,0);drive(GPIOF,6,1);
 PWR->SVMCR1|=PWR_SVMCR1_VDDIO4SV;__DSB();
 drive(GPIOC,12,1);
 uint32_t excited=DWT->CYCCNT;
 knob_proof[K_SVMCR1_DURING]=PWR->SVMCR1;

 /* Converter bring-up, as proven by vbus.c and the control diagnostic. */
 result=KNOB_SUPPLY;
 RIFSC->RISC_SECCFGRx[2]|=1U;__DSB();
 PWR->SVMCR3|=PWR_SVMCR3_AVMEN;
 while(!(PWR->SVMCR3&PWR_SVMCR3_ARDY)){if(HAL_GetTick()-start>20U)goto cleanup;}
 PWR->SVMCR3|=PWR_SVMCR3_ASV;__DSB();
 RCC->AHB1RSTSR=RCC_AHB1RSTR_ADC12RST;__DSB();RCC->AHB1RSTCR=RCC_AHB1RSTR_ADC12RST;__DSB();
 LL_RCC_SetADCPrescaler(7U);LL_RCC_SetADCClockSource(LL_RCC_ADC_CLKSOURCE_HSI);
 RCC->AHB1ENSR=RCC_AHB1ENR_ADC12EN;__DSB();
 adc.Instance=ADC1;adc.Init.Resolution=ADC_RESOLUTION_12B;adc.Init.ScanConvMode=ADC_SCAN_DISABLE;
 adc.Init.EOCSelection=ADC_EOC_SINGLE_CONV;adc.Init.NbrOfConversion=1;
 adc.Init.ExternalTrigConv=ADC_SOFTWARE_START;adc.Init.ExternalTrigConvEdge=ADC_EXTERNALTRIGCONVEDGE_NONE;
 adc.Init.SamplingMode=ADC_SAMPLING_MODE_NORMAL;adc.Init.ConversionDataManagement=ADC_CONVERSIONDATA_DR;
 adc.Init.Overrun=ADC_OVR_DATA_PRESERVED;
 knob_proof[K_STATE]=2;result=KNOB_ADC_INIT;
 if(HAL_ADC_Init(&adc)!=HAL_OK)goto adc_cleanup;
 result=KNOB_ADC_SETUP;
 {
  ADC_ChannelConfTypeDef ch={0};
  ch.Channel=ADC_CHANNEL_10;ch.Rank=ADC_REGULAR_RANK_1;ch.SamplingTime=ADC_SAMPLETIME_1499CYCLES_5;
  ch.SingleDiff=ADC_SINGLE_ENDED;ch.OffsetNumber=ADC_OFFSET_NONE;
  if(HAL_ADC_ConfigChannel(&adc,&ch)!=HAL_OK||
     HAL_ADCEx_Calibration_Start(&adc,ADC_SINGLE_ENDED)!=HAL_OK)goto adc_cleanup;
 }
 while((uint32_t)(DWT->CYCCNT-excited)<SETTLE_CYCLES)__NOP();
 knob_proof[K_SETTLE_CYCLES]=DWT->CYCCNT-excited;
 knob_proof[K_STATE]=3;result=KNOB_CONVERSION;
 /* Two interleaved readings of each knob. The second pair is used; the
  * first shows on the bench whether the inputs had settled. */
 if(!convert(&adc,ADC_CHANNEL_10,&knob_proof[K_EXPOSURE_FIRST])||
    !convert(&adc,ADC_CHANNEL_7,&knob_proof[K_GAIN_FIRST])||
    !convert(&adc,ADC_CHANNEL_10,&knob_proof[K_EXPOSURE_CODE])||
    !convert(&adc,ADC_CHANNEL_7,&knob_proof[K_GAIN_CODE]))goto adc_cleanup;
 knob_proof[K_STATE]=4;
 {
  struct knob_setting setting=knob_map(knob_proof[K_EXPOSURE_CODE],knob_proof[K_GAIN_CODE]);
  result=patch(setting);
  if(result==KNOB_APPLIED){
   knob_proof[K_LINES]=setting.lines;knob_proof[K_FRAME]=setting.frame;knob_proof[K_GAIN]=setting.gain;
   knob_proof[K_STATE]=5;
  }
 }
adc_cleanup:
 knob_proof[K_ADC_ERROR]=adc.ErrorCode;knob_proof[K_ADC_ISR]=ADC1->ISR;knob_proof[K_CALFACT]=ADC1->CALFACT;
 HAL_ADC_Stop(&adc);HAL_ADC_DeInit(&adc);RCC->AHB1ENCR=RCC_AHB1ENR_ADC12EN;
cleanup:
 /* Remove excitation first, then hand every pin and supply bit back. */
 GPIOF->BSRR=1U<<(6U+16U);GPIOC->BSRR=1U<<(12U+16U);__DSB();
 for(unsigned i=0;i<PIN_REGISTERS;i++)*pin_registers[i]=pins[i];
 __DSB();
 PWR->SVMCR1=(PWR->SVMCR1&~PWR_SVMCR1_VDDIO4SV)|(bank&PWR_SVMCR1_VDDIO4SV);
 RCC->CCIPR1=(RCC->CCIPR1&~(RCC_CCIPR1_ADC12SEL|RCC_CCIPR1_ADCPRE))|(mux&(RCC_CCIPR1_ADC12SEL|RCC_CCIPR1_ADCPRE));
 RIFSC->RISC_SECCFGRx[2]=security;
 PWR->SVMCR3=(PWR->SVMCR3&~(PWR_SVMCR3_AVMEN|PWR_SVMCR3_ASV))|(supply&(PWR_SVMCR3_AVMEN|PWR_SVMCR3_ASV));
 if(!(ahb3&RCC_AHB3ENR_RIFSCEN))RCC->AHB3ENCR=RCC_AHB3ENR_RIFSCEN;
 RCC->AHB4ENCR=(~ahb4)&clocks;__DSB();
 knob_proof[K_RESULT]=result;knob_proof[K_TOTAL_CYCLES]=DWT->CYCCNT-began;
 return result;
}
