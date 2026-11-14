/* Host run of the real knob.c and the real ST HAL ADC driver against a small
 * model of the bus. The simpler register model in test_knob.py stands in for
 * the driver, and once let a driver rule slip through: a channel cannot be
 * changed while the converter is enabled. This model runs the driver itself.
 *
 * ADC_CR follows RM0486: ADEN, ADDIS, ADSTART and ADSTP are set-only from
 * software, and ADEN falls only after ADDIS. A conversion counts as valid
 * only while both knobs are excited and the analog path is closed.
 * Linux only (fixed-address mmap). Usage: model stage1.bin exposure gain [v]
 */
#include "stm32n6xx_hal.h"
#include <sys/mman.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

uint32_t SystemCoreClock=400000000U;
MPU_Type model_mpu;
extern uint32_t knob_apply(void);
extern volatile uint32_t knob_proof[32];
static uint32_t adc_resets,code10,code7,conversions,bad_state,verbose;

static void map(uintptr_t base,size_t len){
 void *p=mmap((void *)base,len,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
 if(p!=(void *)base){perror("mmap");exit(2);}
}
static void adc_reset(ADC_TypeDef *a){memset((void *)a,0,0x100);a->CR=ADC_CR_DEEPPWD;}
static const char *name(ADC_TypeDef *a){return a==ADC1?"ADC1":"ADC2";}

uint32_t sim_write(volatile uint32_t *reg,uint32_t v)
{
 ADC_TypeDef *a=0;
 if(reg==&ADC1->CR)a=ADC1;else if(reg==&ADC2->CR)a=ADC2;
 if(a){
  const uint32_t rs=0x3FU;uint32_t old=a->CR,n=(v&~rs)|(old&rs)|(v&rs);
  if(!(RCC->AHB1ENR&RCC_AHB1ENR_ADC12EN)){printf("  !! %s CR written with ADC12 clock off\n",name(a));bad_state++;}
  if((v&ADC_CR_ADEN)&&!(old&ADC_CR_ADEN)){
   if(n&ADC_CR_DEEPPWD){printf("  !! ADEN while DEEPPWD\n");bad_state++;}
   a->ISR|=ADC_ISR_ADRDY;
  }
  if(n&ADC_CR_ADDIS){
   if(n&(ADC_CR_ADSTART|ADC_CR_JADSTART)){printf("  !! ADDIS during conversion\n");bad_state++;}
   else n&=~(ADC_CR_ADEN|ADC_CR_ADDIS);
  }
  if(v&ADC_CR_ADSTP)n&=~(ADC_CR_ADSTART|ADC_CR_ADSTP);
  if((v&ADC_CR_ADSTART)&&!(n&ADC_CR_ADEN)){printf("  !! ADSTART while disabled\n");bad_state++;n&=~ADC_CR_ADSTART;}
  a->CR=n;
  if(verbose)printf("  %s CR write %08x: %08x -> %08x\n",name(a),v,old,n);
  return n;
 }
 if(reg==&ADC1->ISR||reg==&ADC2->ISR){*reg&=~v;return *reg;}
 if(reg==&ADC1->PCSEL&&verbose)printf("  ADC1 PCSEL <- %08x (ADEN=%u)\n",v,(unsigned)(ADC1->CR&1U));
 if(reg==&ADC1->SQR1&&verbose)printf("  ADC1 SQR1  <- %08x (ADEN=%u)\n",v,(unsigned)(ADC1->CR&1U));
 *reg=v;return v;
}

static void port(GPIO_TypeDef *g){g->ODR=(g->ODR|(g->BSRR&65535U))&~(g->BSRR>>16);g->BSRR=0;}
static uint32_t sample(ADC_TypeDef *a)
{
 uint32_t channel=(a->SQR1>>ADC_SQR1_SQ1_Pos)&31U;conversions++;
 /* A reading is only meaningful with the pots excited and the analog path closed. */
 unsigned ok=(GPIOF->MODER>>10&3U)==1U&&!(GPIOF->ODR&32U)&&(GPIOF->MODER>>12&3U)==1U&&(GPIOF->ODR&64U)&&
  (GPIOC->MODER>>24&3U)==1U&&(GPIOC->ODR&4096U)&&(PWR->SVMCR1&PWR_SVMCR1_VDDIO4SV)&&
  (GPIOA->MODER>>18&3U)==3U&&(GPIOG->MODER>>30)==3U&&(RIFSC->RISC_SECCFGRx[2]&1U)&&(PWR->SVMCR3&PWR_SVMCR3_ASV)&&
  (a->PCSEL>>channel&1U);
 if(!ok){printf("  !! conversion of channel %u without excitation/path\n",(unsigned)channel);bad_state++;}
 if(verbose)printf("  conversion #%u channel %u at CYCCNT %u\n",(unsigned)conversions,(unsigned)channel,(unsigned)DWT->CYCCNT);
 return channel==10U?code10:channel==7U?code7:channel==5U?0U:3840U;
}
void sim_sync(void)
{
 RCC->AHB4ENR=(RCC->AHB4ENR|RCC->AHB4ENSR)&~RCC->AHB4ENCR;RCC->AHB4ENSR=RCC->AHB4ENCR=0;
 RCC->AHB3ENR=(RCC->AHB3ENR|RCC->AHB3ENSR)&~RCC->AHB3ENCR;RCC->AHB3ENSR=RCC->AHB3ENCR=0;
 RCC->AHB1ENR=(RCC->AHB1ENR|RCC->AHB1ENSR)&~RCC->AHB1ENCR;RCC->AHB1ENSR=RCC->AHB1ENCR=0;
 if(RCC->AHB1RSTSR&RCC_AHB1RSTR_ADC12RST){adc_reset(ADC1);adc_reset(ADC2);ADC12_COMMON->CCR=0;adc_resets++;}
 RCC->AHB1RSTSR=RCC->AHB1RSTCR=0;
 port(GPIOA);port(GPIOC);port(GPIOF);port(GPIOG);port(GPIOH);
 if(PWR->SVMCR3&PWR_SVMCR3_AVMEN)PWR->SVMCR3|=PWR_SVMCR3_ARDY;else PWR->SVMCR3&=~PWR_SVMCR3_ARDY;
 DWT->CYCCNT+=4000U;
 ADC_TypeDef *both[2]={ADC1,ADC2};
 for(unsigned i=0;i<2;i++){ADC_TypeDef *a=both[i];
  if(a->CR&ADC_CR_ADSTART){a->DR=(a->CR&ADC_CR_ADCAL)?6U:sample(a);a->ISR|=ADC_ISR_EOC|ADC_ISR_EOS;a->CR&=~ADC_CR_ADSTART;}
 }
}
void sim_nop(void){DWT->CYCCNT+=400U;}
uint32_t HAL_GetTick(void){sim_sync();return DWT->CYCCNT/400000U;}

typedef struct {uint32_t rcc[4],gpio[5][5],pwr[2],rifsc,adc1cr;} State;
static State snapshot(void)
{
 sim_sync();State s;GPIO_TypeDef *g[5]={GPIOA,GPIOC,GPIOF,GPIOG,GPIOH};
 s.rcc[0]=RCC->AHB4ENR;s.rcc[1]=RCC->AHB3ENR;s.rcc[2]=RCC->AHB1ENR;s.rcc[3]=RCC->CCIPR1;
 for(unsigned i=0;i<5;i++){s.gpio[i][0]=g[i]->MODER;s.gpio[i][1]=g[i]->PUPDR;s.gpio[i][2]=g[i]->OTYPER;s.gpio[i][3]=g[i]->OSPEEDR;s.gpio[i][4]=g[i]->ODR;}
 s.pwr[0]=PWR->SVMCR1;s.pwr[1]=PWR->SVMCR3&~PWR_SVMCR3_ARDY;s.rifsc=RIFSC->RISC_SECCFGRx[2];s.adc1cr=ADC1->CR;
 return s;
}

#include "capture_controls.h"
int main(int argc,char **argv){map(0x34180000UL,0x2000);map(0x343F0000UL,0x10000);map(0x50022000UL,0x1000);map(0x54024000UL,0x1000);map(0x56020000UL,0xA000);map(0xE0001000UL,0x1000);code10=strtoul(argv[1],0,0);code7=strtoul(argv[2],0,0);GPIO_TypeDef *g[5]={GPIOA,GPIOC,GPIOF,GPIOG,GPIOH};for(unsigned i=0;i<5;i++){g[i]->MODER=0xFFFFFFFFU;g[i]->SECCFGR=0xFFFFU;}RCC->AHB4ENR=0x18U|0x4000U;PWR->SVMCR3=0x100U;adc_reset(ADC1);adc_reset(ADC2);DWT->CYCCNT=123456U;capture_controls_sample();volatile capture_controls_t *r=CAPTURE_CONTROLS;printf("ours codes %u/%u state %u error %u flags %u conversions %u violations %u low %u high %u/%u raw %u/%u us %u gain %u valid %u\n",code10,code7,r->state,r->error,r->flags,conversions,bad_state,r->adc_low,r->exposure_high,r->asa_high,r->exposure_raw,r->asa_raw,r->requested_us,r->manual[1],capture_controls_valid(r));return r->error||bad_state;}
