/* Canonical controls sampler + unmodified ST HAL ADC/ADCEx, host execution.
 * The bus model supplies hardware side effects, not HAL success responses.
 * It does not model analog settling, real clock rates, or electrical faults.
 */
#include "stm32n6xx_hal.h"
#include "stm32n6xx_ll_rcc.h"
#include "capture_controls.h"
#include "host_memory.h"
#include <assert.h>
#include <string.h>
_Static_assert(sizeof(uintptr_t) == 8, "ADC model requires a 64-bit host compiler");

uint32_t SystemCoreClock = 400000000U;
MPU_Type model_mpu;
static unsigned resets, conversions, violations, calibrations;
static unsigned conversion_is_calibration[2];
static uint32_t exposure_code, gain_code;
static const char *fault;
static int is_fault(const char *s) { return strcmp(fault, s) == 0; }
static void reset_adc(ADC_TypeDef *a) { memset((void *)a, 0, 0x100); a->CR = ADC_CR_DEEPPWD; }

uint32_t sim_write(volatile uint32_t *reg, uint32_t value)
{
  ADC_TypeDef *a = reg == &ADC1->CR ? ADC1 : reg == &ADC2->CR ? ADC2 : NULL;
  if (a) {
    /* ADEN/ADDIS/ADSTART/ADSTP are set-only requests, not normal RAM bits. */
    const uint32_t requests = 0x3FU;
    uint32_t old = a->CR, next = (value & ~requests) | (old & requests) | (value & requests);
    if ((value & ADC_CR_ADSTART) && !(old & ADC_CR_ADSTART))
      conversion_is_calibration[a == ADC2] = !!(next & ADC_CR_ADCAL);
    if (!(RCC->AHB1ENR & RCC_AHB1ENR_ADC12EN)) violations++;
    if ((value & ADC_CR_ADEN) && !(old & ADC_CR_ADEN)) {
      if (next & ADC_CR_DEEPPWD) violations++;
      if (!is_fault("ready_timeout")) a->ISR |= ADC_ISR_ADRDY;
    }
    if (next & ADC_CR_ADDIS) {
      if (next & (ADC_CR_ADSTART | ADC_CR_JADSTART)) violations++;
      else next &= ~(ADC_CR_ADEN | ADC_CR_ADDIS);
    }
    if (value & ADC_CR_ADSTP) next &= ~(ADC_CR_ADSTART | ADC_CR_ADSTP);
    if ((value & ADC_CR_ADSTART) && !(next & ADC_CR_ADEN)) {
      violations++; next &= ~ADC_CR_ADSTART;
    }
    a->CR = next;
    return next;
  }
  if (reg == &ADC1->ISR || reg == &ADC2->ISR) { *reg &= ~value; return *reg; }
  if ((reg == &ADC1->PCSEL || reg == &ADC1->DIFSEL) &&
      (ADC1->CR & ADC_CR_ADEN) && *reg != value) violations++;
  *reg = value;
  return value;
}

static void gpio(GPIO_TypeDef *g)
{
  g->ODR = (g->ODR | (g->BSRR & 65535U)) & ~(g->BSRR >> 16);
  g->BSRR = 0;
}

static uint32_t sample(ADC_TypeDef *a)
{
  uint32_t channel = (a->SQR1 >> ADC_SQR1_SQ1_Pos) & 31U;
  static const unsigned order[5] = {5, 11, 16, 10, 7};
  if (conversions >= 5 || channel != order[conversions]) violations++;
  conversions++;
  /* Both pots excited, endpoints correct, analog isolation closed, preselected. */
  if ((GPIOF->MODER >> 10 & 3U) != 1 || (GPIOF->ODR & 32U) ||
      (GPIOF->MODER >> 12 & 3U) != 1 || !(GPIOF->ODR & 64U) ||
      (GPIOC->MODER >> 24 & 3U) != 1 || !(GPIOC->ODR & 4096U) ||
      !(PWR->SVMCR1 & PWR_SVMCR1_VDDIO4SV) ||
      !(PWR->SVMCR3 & PWR_SVMCR3_ASV) || !(RIFSC->RISC_SECCFGRx[2] & 1U) ||
      (GPIOA->MODER & 0x3F0000U) != 0x3F0000U ||
      (GPIOF->MODER >> 6 & 3U) != 3 || (GPIOG->MODER >> 30) != 3 ||
      (GPIOC->MODER >> 20 & 3U) || (GPIOH->MODER >> 4 & 3U) ||
      !(a->PCSEL & (1U << channel))) violations++;
  if (LL_RCC_GetADCClockSource(LL_RCC_ADC_CLKSOURCE) != LL_RCC_ADC_CLKSOURCE_HCLK ||
      LL_RCC_GetADCPrescaler() != 31U) violations++;
  if (channel == 5) return 0;
  if (channel == 11) return is_fault("bad_reference") ? 2000 : 3840;
  if (channel == 16) return 3840;
  return channel == 10 ? exposure_code : gain_code;
}

void sim_sync(void)
{
  RCC->AHB4ENR = (RCC->AHB4ENR | RCC->AHB4ENSR) & ~RCC->AHB4ENCR;
  RCC->AHB4ENSR = RCC->AHB4ENCR = 0;
  RCC->AHB3ENR = (RCC->AHB3ENR | RCC->AHB3ENSR) & ~RCC->AHB3ENCR;
  RCC->AHB3ENSR = RCC->AHB3ENCR = 0;
  RCC->AHB1ENR = (RCC->AHB1ENR | RCC->AHB1ENSR) & ~RCC->AHB1ENCR;
  RCC->AHB1ENSR = RCC->AHB1ENCR = 0;
  if (RCC->AHB1RSTSR & RCC_AHB1RSTR_ADC12RST) {
    reset_adc(ADC1); reset_adc(ADC2); ADC12_COMMON->CCR = 0; resets++;
  }
  RCC->AHB1RSTSR = RCC->AHB1RSTCR = 0;
  gpio(GPIOA); gpio(GPIOC); gpio(GPIOF); gpio(GPIOG); gpio(GPIOH);
  if ((PWR->SVMCR3 & PWR_SVMCR3_AVMEN) && !is_fault("supply_timeout"))
    PWR->SVMCR3 |= PWR_SVMCR3_ARDY;
  else PWR->SVMCR3 &= ~PWR_SVMCR3_ARDY;
  DWT->CYCCNT += 4000U;
  ADC_TypeDef *both[2] = {ADC1, ADC2};
  for (unsigned i = 0; i < 2; i++) {
    ADC_TypeDef *a = both[i];
    if (!(a->CR & ADC_CR_ADSTART)) continue;
    if (conversion_is_calibration[i]) {
      if (is_fault("calibration_timeout")) continue;
      calibrations++; a->DR = 6;
    } else {
      if (is_fault("conversion_timeout") && conversions == 2) continue;
      a->DR = sample(a);
    }
    a->ISR |= ADC_ISR_EOC | ADC_ISR_EOS;
    a->CR &= ~ADC_CR_ADSTART;
  }
}
void sim_nop(void) { DWT->CYCCNT += 400U; }
uint32_t HAL_GetTick(void) { sim_sync(); return DWT->CYCCNT / 400000U; }

/* COFF retains unused driver sections differently from ELF. These DMA paths
 * are never used by this polling-only sampler; fail hard if that changes. */
HAL_StatusTypeDef HAL_DMAEx_List_GetNodeConfig(DMA_NodeConfTypeDef *const c, DMA_NodeTypeDef const *const n)
{ (void)c; (void)n; abort(); }
HAL_StatusTypeDef HAL_DMAEx_List_Start_IT(DMA_HandleTypeDef *const h)
{ (void)h; abort(); }
HAL_StatusTypeDef HAL_DMA_Start_IT(DMA_HandleTypeDef *const h, uint32_t s, uint32_t d, uint32_t n)
{ (void)h; (void)s; (void)d; (void)n; abort(); }
HAL_StatusTypeDef HAL_DMA_Abort(DMA_HandleTypeDef *const h)
{ (void)h; abort(); }

int main(int argc, char **argv)
{
  if (argc != 4) return 2;
  fault = argv[1]; exposure_code = strtoul(argv[2], NULL, 0); gain_code = strtoul(argv[3], NULL, 0);
  model_map(0x343F0000UL, 0x10000); model_map(0x50022000UL, 0x1000);
  model_map(0x54024000UL, 0x1000); model_map(0x56020000UL, 0xA000); model_map(0xE0001000UL, 0x1000);
  GPIO_TypeDef *ports[7] = {GPIOA, GPIOC, GPIOD, GPIOE, GPIOF, GPIOG, GPIOH};
  for (unsigned i = 0; i < 7; i++) { ports[i]->MODER = 0xFFFFFFFFU; ports[i]->SECCFGR = 0xFFFFU; }
  GPIOD->MODER = GPIOE->MODER = 0x13579BDFU;
  GPIOD->ODR = GPIOE->ODR = 0x5AA5U;
  GPIOA->PUPDR = 0x20U; /* Former HOLD PA2 must remain untouched. */
  RCC->AHB4ENR = 0x18U | 0x4000U; RCC->CCIPR1 = 0xABCD7654U;
  PWR->SVMCR1 = is_fault("wrong_voltage") ? PWR_SVMCR1_VDDIO4VRSEL : 0;
  PWR->SVMCR3 = 0x100U; RIFSC->RISC_SECCFGRx[2] = 0x80000000U;
  RIFSC->RISC_PRIVCFGRx[2] = 0x12345678U;
  if (is_fault("missing_security")) GPIOA->SECCFGR = 0;
  reset_adc(ADC1); reset_adc(ADC2); DWT->CYCCNT = 123456U;
  if (is_fault("busy_adc")) { RCC->AHB1ENR = RCC_AHB1ENR_ADC12EN; ADC1->CR = ADC_CR_ADEN; }
  uint32_t ahb1 = RCC->AHB1ENR, ahb4 = RCC->AHB4ENR, bank = PWR->SVMCR1;
  capture_controls_sample();
  const volatile capture_controls_t *r = CAPTURE_CONTROLS;
  assert(r->crc32 == capture_controls_crc(r));
  assert(!(GPIOF->ODR & 64U) && !(GPIOC->ODR & 4096U));
  assert(r->flags & CC_F_EXCITATION_OFF);
  assert(RCC->AHB1ENR == ahb1 && RCC->AHB3ENR == 0 && RCC->AHB4ENR == ahb4);
  assert(RCC->CCIPR1 == 0xABCD7654U && PWR->SVMCR1 == bank && PWR->SVMCR3 == 0x100U);
  assert(RIFSC->RISC_SECCFGRx[2] == 0x80000000U && RIFSC->RISC_PRIVCFGRx[2] == 0x12345678U);
  assert(GPIOD->MODER == 0x13579BDFU && GPIOE->MODER == 0x13579BDFU);
  assert(GPIOD->ODR == 0x5AA5U && GPIOE->ODR == 0x5AA5U);
  assert((GPIOA->MODER & 0x30U) == 0x30U && (GPIOA->PUPDR & 0x30U) == 0x20U);
  if (is_fault("busy_adc")) assert(ADC1->CR == ADC_CR_ADEN && resets == 0);
  else assert(!(ADC1->CR & (ADC_CR_ADEN | ADC_CR_ADSTART | ADC_CR_JADSTART | ADC_CR_ADSTP)));
  assert(violations == 0);
  if (!r->error) {
    assert(r->state == CC_ADC_READY && capture_controls_valid(r));
    assert(conversions == 5 && calibrations && resets == 1);
    assert(r->exposure_raw == exposure_code && r->asa_raw == gain_code);
  } else assert(r->state == CC_FAILED && !(r->flags & CC_F_ADC_VALID));
  printf("fault=%s error=%u conversions=%u calibrations=%u violations=%u us=%u asa=%u cleanup=ok\n",
         fault, (unsigned)r->error, conversions, calibrations, violations, (unsigned)r->requested_us, (unsigned)r->asa);
  return 0;
}
