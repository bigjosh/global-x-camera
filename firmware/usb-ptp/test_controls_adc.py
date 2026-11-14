"""Execute actual ADC cleanup/security paths against native register/HAL fakes."""
from pathlib import Path
import shutil,subprocess,tempfile,unittest
HERE=Path(__file__).resolve().parent
class ADCTests(unittest.TestCase):
 def test_success_and_faults_always_remove_excitation(self):
  cc=shutil.which('clang') or shutil.which('gcc')
  if not cc:self.skipTest('Native compiler unavailable')
  with tempfile.TemporaryDirectory(prefix='controls-adc-') as t:
   p=Path(t)
   h=(HERE/'capture_controls.h').read_text().replace('0x343F9400U','((uintptr_t)cc_record_words)')
   (p/'capture_controls.h').write_text(h)
   (p/'capture_controls_adc.c').write_text((HERE/'capture_controls_adc.c').read_text())
   (p/'capture_controls_map.c').write_text((HERE/'capture_controls_map.c').read_text())
   (p/'stm32n6xx_hal.h').write_text(MOCK)
   (p/'stm32n6xx_ll_rcc.h').write_text('#define LL_RCC_ADC_CLKSOURCE_HCLK 0\nvoid LL_RCC_SetADCPrescaler(unsigned);void LL_RCC_SetADCClockSource(unsigned);\n')
   (p/'test.c').write_text(HARNESS)
   r=subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-I'+str(p),str(p/'test.c'),str(p/'capture_controls_adc.c'),str(p/'capture_controls_map.c'),'-o',str(p/'test.exe')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([str(p/'test.exe')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
MOCK=r'''
#ifndef MOCK_HAL_H
#define MOCK_HAL_H
#include <stdint.h>
typedef struct {uint32_t BSRR,OTYPER,PUPDR,OSPEEDR,MODER,SECCFGR,ODR;} GPIO_TypeDef;
typedef struct {uint32_t AHB1ENR,AHB3ENR,AHB4ENR,AHB4ENSR,AHB3ENSR,AHB1RSTSR,AHB1RSTCR,AHB1ENSR,AHB1ENCR,AHB3ENCR,AHB4ENCR,CCIPR1;} RCC_TypeDef;
typedef struct {uint32_t SVMCR1,SVMCR3;} PWR_TypeDef;
typedef struct {uint32_t RISC_SECCFGRx[3],RISC_PRIVCFGRx[3];} RIF_TypeDef;
typedef struct {uint32_t CYCCNT;} DWT_TypeDef;
extern GPIO_TypeDef ga,gc,gf,gg,gh;extern RCC_TypeDef rcc;extern PWR_TypeDef pwr;extern RIF_TypeDef rif;extern DWT_TypeDef dwt;
extern uint32_t cc_record_words[32];
#define GPIOA (&ga)
#define GPIOC (&gc)
#define GPIOF (&gf)
#define GPIOG (&gg)
#define GPIOH (&gh)
#define RCC (&rcc)
#define PWR (&pwr)
#define RIFSC (&rif)
#define DWT (&dwt)
#define RCC_AHB4ENR_GPIOAEN 1U
#define RCC_AHB4ENR_GPIOCEN 4U
#define RCC_AHB4ENR_GPIOFEN 32U
#define RCC_AHB4ENR_GPIOGEN 64U
#define RCC_AHB4ENR_GPIOHEN 128U
#define RCC_AHB4ENR_PWREN 256U
#define RCC_AHB3ENR_RIFSCEN 1U
#define RCC_AHB1ENR_ADC12EN 1U
#define RCC_AHB1RSTR_ADC12RST 1U
#define RCC_CCIPR1_ADC12SEL 0xF0U
#define RCC_CCIPR1_ADCPRE 0x1F00U
#define PWR_SVMCR1_VDDIO4VRSEL 1U
#define PWR_SVMCR1_VDDIO4SV 2U
#define PWR_SVMCR3_AVMEN 1U
#define PWR_SVMCR3_ARDY 2U
#define PWR_SVMCR3_ASV 4U
#define ADC_CHANNEL_5 5U
#define ADC_CHANNEL_7 7U
#define ADC_CHANNEL_10 10U
#define ADC_CHANNEL_11 11U
#define ADC_CHANNEL_16 16U
#define ADC1 ((void *)1)
#define HAL_OK 0
#define ADC_REGULAR_RANK_1 1
#define ADC_SAMPLETIME_1499CYCLES_5 1499
#define ADC_SINGLE_ENDED 0
#define ADC_OFFSET_NONE 0
#define ADC_RESOLUTION_12B 12
#define ADC_SCAN_DISABLE 0
#define ADC_EOC_SINGLE_CONV 1
#define ADC_SOFTWARE_START 1
#define ADC_EXTERNALTRIGCONVEDGE_NONE 0
#define ADC_SAMPLING_MODE_NORMAL 0
#define ADC_CONVERSIONDATA_DR 0
#define ADC_OVR_DATA_PRESERVED 0
typedef struct {uint32_t Resolution,ScanConvMode,EOCSelection,NbrOfConversion,ExternalTrigConv,ExternalTrigConvEdge,SamplingMode,ConversionDataManagement,Overrun;} Init;
typedef struct {void *Instance;Init Init;} ADC_HandleTypeDef;
typedef struct {uint32_t Channel,Rank,SamplingTime,SingleDiff,OffsetNumber;} ADC_ChannelConfTypeDef;
int HAL_ADC_Stop(ADC_HandleTypeDef*);int HAL_ADC_Init(ADC_HandleTypeDef*);int HAL_ADC_DeInit(ADC_HandleTypeDef*);
int HAL_ADC_ConfigChannel(ADC_HandleTypeDef*,ADC_ChannelConfTypeDef*);int HAL_ADC_Start(ADC_HandleTypeDef*);
int HAL_ADC_PollForConversion(ADC_HandleTypeDef*,unsigned);uint32_t HAL_ADC_GetValue(ADC_HandleTypeDef*);
int HAL_ADCEx_Calibration_Start(ADC_HandleTypeDef*,unsigned);uint32_t HAL_GetTick(void);void sync_regs(void);
#define __DSB() sync_regs()
#define __NOP() ((void)0)
#endif
'''
HARNESS=r'''
#include "stm32n6xx_hal.h"
#include "capture_controls.h"
#include <assert.h>
#include <string.h>
GPIO_TypeDef ga,gc,gf,gg,gh;RCC_TypeDef rcc;PWR_TypeDef pwr;RIF_TypeDef rif;DWT_TypeDef dwt;uint32_t cc_record_words[32];
static unsigned failure,channel,samples,ticks,saw_high,saw_secure,reset_count;
static void gpio(GPIO_TypeDef *p){p->ODR=(p->ODR|(p->BSRR&65535))&~(p->BSRR>>16);p->BSRR=0;}
void sync_regs(void){gpio(&ga);gpio(&gc);gpio(&gf);gpio(&gg);gpio(&gh);if(gf.ODR&64)saw_high++;if(rif.RISC_SECCFGRx[2]&1)saw_secure++;
 rcc.AHB4ENR=(rcc.AHB4ENR|rcc.AHB4ENSR)&~rcc.AHB4ENCR;rcc.AHB4ENSR=rcc.AHB4ENCR=0;
 rcc.AHB3ENR=(rcc.AHB3ENR|rcc.AHB3ENSR)&~rcc.AHB3ENCR;rcc.AHB3ENSR=rcc.AHB3ENCR=0;
 rcc.AHB1ENR=(rcc.AHB1ENR|rcc.AHB1ENSR)&~rcc.AHB1ENCR;rcc.AHB1ENSR=rcc.AHB1ENCR=0;
 if(rcc.AHB1RSTSR){reset_count++;rcc.AHB1RSTSR=0;}
}
uint32_t HAL_GetTick(void){dwt.CYCCNT+=400000;return ticks++;}
void LL_RCC_SetADCPrescaler(unsigned n){assert(n==31);rcc.CCIPR1=(rcc.CCIPR1&~0x1F00U)|(n<<8);}
void LL_RCC_SetADCClockSource(unsigned n){assert(n==0);rcc.CCIPR1&=~0xF0U;}
int HAL_ADC_Init(ADC_HandleTypeDef *a){assert(rif.RISC_SECCFGRx[2]&1);return failure==2;}
int HAL_ADC_DeInit(ADC_HandleTypeDef *a){return failure==13;}
int HAL_ADCEx_Calibration_Start(ADC_HandleTypeDef *a,unsigned n){return failure==3;}
int HAL_ADC_Stop(ADC_HandleTypeDef *a){return failure==4||(failure==12&&samples==5);}
int HAL_ADC_ConfigChannel(ADC_HandleTypeDef *a,ADC_ChannelConfTypeDef *c){channel=c->Channel;assert(c->SamplingTime==1499);return failure==5;}
int HAL_ADC_Start(ADC_HandleTypeDef *a){assert(rif.RISC_SECCFGRx[2]&1);assert(!(gc.MODER&(3U<<20))&&!(gh.MODER&(3U<<4)));return failure==6;}
int HAL_ADC_PollForConversion(ADC_HandleTypeDef *a,unsigned n){return failure==7;}
uint32_t HAL_ADC_GetValue(ADC_HandleTypeDef *a){samples++;switch(channel){case5:return 2;case11:return failure==8?2000:3840;case16:return3840;case10:return2177;case7:return1781;default:assert(0);return0;}}
static void reset(unsigned f){memset(&ga,0,sizeof ga);memset(&gc,0,sizeof gc);memset(&gf,0,sizeof gf);memset(&gg,0,sizeof gg);memset(&gh,0,sizeof gh);memset(&rcc,0,sizeof rcc);memset(&pwr,0,sizeof pwr);memset(&rif,0,sizeof rif);memset(cc_record_words,0,sizeof cc_record_words);
 ga.SECCFGR=0x700;gf.SECCFGR=8;gg.SECCFGR=1U<<15;ga.MODER=0xA0000030U;ga.PUPDR=0x50000020U;rcc.CCIPR1=0xABCD7654U;rif.RISC_SECCFGRx[2]=0x80000000U;rif.RISC_PRIVCFGRx[2]=0x12345678U;pwr.SVMCR3=2;
 failure=f;samples=ticks=saw_high=saw_secure=reset_count=0;
 if(f==1)rcc.AHB1ENR=1;if(f==9)ga.SECCFGR=0;if(f==10)pwr.SVMCR1=1;if(f==11)pwr.SVMCR3=0;
}
int main(void){for(unsigned f=0;f<=13;f++){reset(f);capture_controls_sample();sync_regs();capture_controls_t *r=(capture_controls_t *)cc_record_words;
 assert(!(gf.ODR&64)&&!(gc.ODR&(1U<<12)));assert(r->flags&CC_F_EXCITATION_OFF);assert(r->crc32==capture_controls_crc(r));
 assert((ga.MODER&0x30U)==0x30U&&(ga.PUPDR&0x30U)==0x20U); /* retiredPA2 unchanged */
 assert(rif.RISC_PRIVCFGRx[2]==0x12345678U&&rif.RISC_SECCFGRx[2]==0x80000000U);assert(rcc.CCIPR1==0xABCD7654U);
 if(!f){assert(r->state==CC_ADC_READY&&r->error==0&&samples==5&&saw_high&&saw_secure);assert(r->exposure_raw==2177&&r->asa_raw==1781&&r->line_length==1280);}
 else{assert(r->state==CC_FAILED&&r->error&&!(r->flags&CC_F_ADC_VALID));}
 if(f==1||f==9||f==10||f==11)assert(reset_count==0&&samples==0&&saw_high==0);
 }return0;}
'''
HARNESS=HARNESS.replace('case5','case 5').replace('case7','case 7').replace('case10','case 10').replace('case11','case 11').replace('case16','case 16').replace('return3840','return 3840').replace('return2177','return 2177').replace('return1781','return 1781').replace('return0','return 0')
if __name__=='__main__':unittest.main()
