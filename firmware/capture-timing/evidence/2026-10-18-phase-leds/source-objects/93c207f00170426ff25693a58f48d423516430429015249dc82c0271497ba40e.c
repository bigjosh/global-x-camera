/* Bench-only reset-to-capture timing harness, October 2026.
 * Uses the pinned ST HAL and VD6G driver; no persistent writes or UART.
 * Native RAW10 padded16 dump preserves the first complete frame, without ISP settling.
 */
#include "stm32n6xx_hal.h"
#include "stm32n6xx_nucleo.h"
#include "stm32n6xx_nucleo_bus.h"
#include "vd6g.h"
#include <stdint.h>
#include <stdarg.h>
#include "status_leds.h"
extern void status_led_complete_sleep(void) __attribute__((noreturn));

#define WIDTH 1120U
#define HEIGHT 1364U
#define BYTES (WIDTH * HEIGHT * 2U)
#define TRACE ((volatile uint32_t *)0x343F0000U)
#define EVENTS ((volatile uint32_t *)0x343F0100U)
#ifndef BENCH_STROBE
#define BENCH_STROBE 1
#endif
#ifndef BENCH_RESET_US
#define BENCH_RESET_US 10000U
#endif
#ifndef BENCH_POLL_US
#define BENCH_POLL_US 10000U
#endif
#ifndef BENCH_STOP_STAGE
#define BENCH_STOP_STAGE 0
#endif
#ifndef BENCH_ROM_CLOCKS
#define BENCH_ROM_CLOCKS 0
#endif
#ifndef BENCH_PREPARE_EARLY
#define BENCH_PREPARE_EARLY 0
#endif
#ifndef BENCH_GPIO_LEVEL
#define BENCH_GPIO_LEVEL -1
#endif
#ifndef BENCH_COARSE_LINES
#define BENCH_COARSE_LINES 0
#endif
#ifndef BENCH_BATCH_CONFIG
#define BENCH_BATCH_CONFIG 0
#endif
#ifndef BENCH_STAGE2
#define BENCH_STAGE2 0
#endif
__attribute__((section(".psram_bss"),aligned(32))) uint8_t g_frame[BYTES];
DCMIPP_HandleTypeDef hcam;
static VD6G_Ctx_t sensor;
static volatile uint32_t frames, vsyncs, errors;
static volatile uint32_t irq_sr0, irq_sr1, irq_ier0, irq_ier1;
static uint32_t write_transactions,write_bytes,read_transactions,read_bytes;
extern int VD6G_BenchPrepare(VD6G_Ctx_t *);
extern int VD6G_BenchStartPrepared(VD6G_Ctx_t *);
extern void baseline_clocks(void);
extern HAL_StatusTypeDef MX_DCMIPP_ClockConfig(DCMIPP_HandleTypeDef *);

/* Called before SystemInit/BSS. No stack-backed state survives this function.
 * This volatile debug opening is the same documented sequence as the verified
 * awake marker. It does not touch OTP or lifecycle configuration. */
void capture_early(void)
{
  if(BENCH_STAGE2) {
    /* Stage 1 has already opened debug, released sensor reset, and started DWT.
     * Preserve its trace origin and GPIO edge parity. BSS is not initialized. */
    uint32_t n=TRACE[2];
    if(TRACE[0]==0x43545031U && n<200) {
      EVENTS[n*4]=207; EVENTS[n*4+1]=DWT->CYCCNT; EVENTS[n*4+2]=0; EVENTS[n*4+3]=400000000U;
      TRACE[2]=n+1; TRACE[1]=207; GPIOE->ODR^=1; __DMB();
    }
    return;
  }
  RCC->AHB4ENSR = RCC_AHB4ENSR_GPIODENS | RCC_AHB4ENSR_GPIOEENS;
  (void)RCC->AHB4ENR;
  GPIOD->MODER = (GPIOD->MODER & ~3U) | 1U;
  GPIOE->MODER = (GPIOE->MODER & ~3U) | 1U;
  GPIOE->BSRR = 1U << 16;
  GPIOD->BSRR = 1;
  RCC->APB4ENSR2 = RCC_APB4ENSR2_BSECENS;
  (void)RCC->APB4ENR2;
  BSEC->DBGCR = 0xB451B400;
  BSEC->AP_UNLOCK = 0xB4;
  RCC->MISCENSR = RCC_MISCENSR_DBGENS;
  RCC->MISCLPENSR = RCC_MISCLPENSR_DBGLPENS;
  (void)RCC->MISCENR;
  DBGMCU->CR |= DBGMCU_CR_DBGCLKEN | DBGMCU_CR_DBG_SLEEP;
  __DSB(); __ISB();
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CYCCNT = 0;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  for (unsigned i = 0; i < 64; ++i) TRACE[i] = 0;
  TRACE[0] = 0x43545031; /* CTP1 */
  TRACE[1] = 1;
  TRACE[2] = 0;
  TRACE[16] = RCC->CFGR1;
  TRACE[17] = RCC->CFGR2;
  TRACE[18] = SCB->CCR;
  TRACE[19] = BSEC->DBGCR;
  TRACE[20] = BSEC->AP_UNLOCK;
  if(BENCH_STOP_STAGE==1) for(;;) __NOP();
}

static void event(uint32_t id)
{
  uint32_t primask = __get_PRIMASK();
  __disable_irq();
  uint32_t n = TRACE[2];
  if (n < 200) {
    EVENTS[n*4] = id;
    EVENTS[n*4+1] = DWT->CYCCNT;
    EVENTS[n*4+2] = HAL_GetTick();
    EVENTS[n*4+3] = SystemCoreClock;
    TRACE[2] = n + 1;
  }
  TRACE[1] = id;
  GPIOE->ODR ^= 1;
  __DMB();
  __set_PRIMASK(primask);
}
void bench_sensor_event(uint32_t id) { event(id); }
uint32_t bench_cycles(void) { return DWT->CYCCNT; }
uint32_t bench_cycles_per_ms(void) { return SystemCoreClock/1000U; }

/* Freerun clock/data separation: bounded observational records, no flag clears.
 * Header32 +32 records of16 words at0x343F8000; prior contents beyond count
 * are deliberately not cleared and must never be decoded as current records. */
#define FAST ((volatile uint32_t *)0x343F8000U)
#define FAST_HEADER_WORDS 32U
#define FAST_MAX_RECORDS 32U
#define FAST_RECORD_WORDS 16U
static volatile uint32_t fast_strobes;
__attribute__((noreturn)) static void fail(uint32_t where,int32_t result);

static void fast_snapshot(uint32_t id)
{
  uint32_t mask=__get_PRIMASK(); __disable_irq();
  uint32_t n=FAST[2];
  if(n<FAST_MAX_RECORDS) {
    volatile uint32_t *r=FAST+FAST_HEADER_WORDS+n*FAST_RECORD_WORDS;
    r[0]=id; r[1]=DWT->CYCCNT; r[2]=HAL_GetTick();
    r[11]=RCC->APB5RSTR;
    if(!(r[11]&RCC_APB5RSTR_CSIRST) &&
       (RCC->APB5ENR&RCC_APB5ENR_CSIEN) && (RCC->DIVENR&RCC_DIVENR_IC18EN)) {
      r[3]=CSI->SR0; r[4]=CSI->SR1; r[5]=CSI->IER0; r[6]=CSI->IER1;
      r[7]=CSI->PRCR; r[8]=CSI->PCR; r[9]=CSI->CR; r[10]=CSI->LMCFGR;
      FAST[4]|=r[3]; FAST[5]|=r[4];
    } else {
      for(unsigned i=3;i<=10;++i) r[i]=0;
      r[7]=0xFFFFFFFFU; FAST[7]++;
    }
    r[12]=(RCC->AHB4ENR&RCC_AHB4ENR_GPIOAEN)?(GPIOA->IDR&1U):0xFFFFFFFFU;
    r[13]=frames; r[14]=vsyncs; r[15]=fast_strobes;
    FAST[2]=n+1U;
  } else FAST[3]++;
  FAST[1]=id; __DMB(); __set_PRIMASK(mask);
}


/* Dedicated current-run ForceRx proof:32 words at0x343F8940, immediately after
 * the separate shutdown proof. Sensor START is already complete in stage1;
 * initialization here precedes every PHY/ForceRx observation, not sensor START.
 * Each observation is {DWT cycle, PMCR, raw SR1}. No flags are cleared/masked. */
#define FORCE ((volatile uint32_t *)0x343F8940U)
static void ready_force_init(void)
{
  for(unsigned i=0;i<32U;++i) FORCE[i]=0;
  FORCE[0]=0x52465231U; /* RFR1 */
  FORCE[1]=1U; FORCE[2]=READY_GATE; FORCE[3]=1U;
  FORCE[4]=((volatile uint32_t *)0x343F4000U)[5];
  FORCE[5]=DWT->CYCCNT; FORCE[28]=40000U;
  __DMB();
}

static void ready_force_guard(void)
{
  uint32_t bus=RCC->APB5ENR, kernel=RCC->DIVENR, reset=RCC->APB5RSTR;
  const uint32_t buses=RCC_APB5ENR_CSIEN|RCC_APB5ENR_DCMIPPEN;
  const uint32_t kernels=RCC_DIVENR_IC18EN|RCC_DIVENR_IC17EN;
  const uint32_t resets=RCC_APB5RSTR_CSIRST|RCC_APB5RSTR_DCMIPPRST;
  /* Compact exact relevant RCC bits: bus[6,2], kernel[17:16] shifted to[9:8],
   * reset[6,2] shifted to[22,18]. A safe read has this word equal to0x344. */
  FORCE[31]=(bus&buses)|(((kernel&kernels)>>16)<<8)|((reset&resets)<<16);
  if((bus&buses)!=buses || (kernel&kernels)!=kernels || (reset&resets)) {
    FORCE[29]=(uint32_t)-1; fail(0xA6,-1);
  }
}

static void ready_force_stop_seen(uint32_t sr,uint32_t cycle);
static void ready_force_observe(unsigned at)
{
  ready_force_guard();
  FORCE[at]=DWT->CYCCNT; FORCE[at+1U]=CSI->PMCR; FORCE[at+2U]=CSI->SR1;
  /* The pre-PEN read is historical only: it cannot prove receive readiness. */
  if(at!=6U) ready_force_stop_seen(FORCE[at+2U],FORCE[at]); __DMB();
}

static void ready_force_before_stop(void)
{
  ready_force_observe(12U); FORCE[3]=4U;
  if(FORCE[13]!=2U) {
    FORCE[29]=(uint32_t)-2; fail(0xA6,-2);
  }
}

static void ready_force_stop_seen(uint32_t sr,uint32_t cycle)
{
  if((sr&CSI_SR1_STOPDL0F) && !FORCE[24]) FORCE[24]=cycle;
  if((sr&CSI_SR1_STOPDL1F) && !FORCE[25]) FORCE[25]=cycle;
  if((sr&(CSI_SR1_STOPDL0F|CSI_SR1_STOPDL1F))==
        (CSI_SR1_STOPDL0F|CSI_SR1_STOPDL1F) && !FORCE[26]) FORCE[26]=cycle;
}

static void ready_force_release(void)
{
  ready_force_observe(15U); FORCE[3]=5U;
  ready_force_observe(18U);
  const uint32_t force=CSI_PMCR_FRXMDL0|CSI_PMCR_FRXMDL1;
  const uint32_t stop=CSI_SR1_STOPDL0F|CSI_SR1_STOPDL1F;
  if((FORCE[17]&stop)!=stop || (FORCE[20]&stop)!=stop) {
    FORCE[29]=(uint32_t)-7; fail(0xA6,-7);
  }
  if(FORCE[19]!=CSI_PMCR_FRXMDL1) {
    FORCE[29]=(uint32_t)-3; fail(0xA6,-3);
  }
  ready_force_guard();
  CLEAR_BIT(CSI->PMCR,force); __DSB();
  ready_force_observe(21U);
  if(FORCE[22]!=(FORCE[19]&~force)) {
    FORCE[29]=(uint32_t)-4; fail(0xA6,-4);
  }
  FORCE[3]=6U; __DMB();
}

static void fast_init(void)
{
  for(unsigned i=0;i<FAST_HEADER_WORDS;++i) FAST[i]=0;
  FAST[0]=0x46505931U; /* FPY1 */
  FAST[6]=READY_GATE; FAST[8]=1U;
  ready_force_init();
  fast_snapshot(399);
}

/* Called with physical reset asserted, then immediately before/after release. */
void fast_phy_hook(unsigned int id)
{
  if(id==405U || id==406U) {
    ready_force_observe(id==405U?6U:9U);
    FORCE[3]=id==405U?2U:3U;
    if(id==405U) {
      ready_force_guard();
      WRITE_REG(CSI->PMCR,CSI_PMCR_FRXMDL0|CSI_PMCR_FRXMDL1); __DSB();
      FORCE[30]=CSI->PMCR;
      if(FORCE[30]!=3U) { FORCE[29]=(uint32_t)-5; fail(0xA6,-5); }
    } else if(FORCE[10]!=3U) { FORCE[29]=(uint32_t)-6; fail(0xA6,-6); }
  }
  if(id==405U) {
    if((CSI->PRCR&CSI_PRCR_PEN) || CSI->PCR!=0x0FU) fail(0xA1,-1);
    if(FAST_DATA_STREAMING) {
      CLEAR_BIT(CSI->PCR,CSI_PCR_DL0EN|CSI_PCR_DL1EN); __DSB();
      if(CSI->PCR!=0x03U) fail(0xA1,-2);
    }
  }
  event(id); fast_snapshot(id);
}

static void fast_streaming_data_enable(void)
{
  event(437); fast_snapshot(437);
  FAST[11]=DWT->CYCCNT; FAST[13]=GPIOA->IDR&1U;
  FAST[14]=frames; FAST[15]=vsyncs;
  if(!(CSI->PRCR&CSI_PRCR_PEN)) fail(0xA1,-3);
  if(FAST_DATA_STREAMING) {
    if(CSI->PCR!=0x03U) fail(0xA1,-4);
    SET_BIT(CSI->PCR,CSI_PCR_DL0EN|CSI_PCR_DL1EN); __DSB();
  }
  if(CSI->PCR!=0x0FU) fail(0xA1,-5);
  FAST[12]=DWT->CYCCNT;
  event(438); fast_snapshot(438);
  /* Freerun exposure may already be high. Do not reject it.
   * The bench must associate the captured frame with the first STROBE. */
}

static void fast_qualify_stop(void)
{
  const uint32_t stop_data=CSI_SR1_STOPDL0F|CSI_SR1_STOPDL1F;
  uint32_t begun=HAL_GetTick(),stable=0;
  for(unsigned attempts=0;attempts<10000000U;++attempts) {
    ready_force_guard();
    uint32_t sr=CSI->SR1, observed=DWT->CYCCNT;
    ready_force_stop_seen(sr,observed);
    if((sr&stop_data)==stop_data) {
      if(!stable) stable=DWT->CYCCNT;
      /* Empirical observation gate inherited from v33, not specified T_INIT. */
      if((uint32_t)(DWT->CYCCNT-stable)>=40000U) {
        FORCE[27]=stable;
        FAST[20]=sr; FAST[21]=DWT->CYCCNT;
        event(409); fast_snapshot(409); return;
      }
    } else stable=0;
    if(HAL_GetTick()-begun>50U) break;
  }
  fail(0xA3,-100);
}

#if FAST_SHUTDOWN_DATA_OFF
/* Separate64-byte proof buffer; FAST544words ends at0x343F8880. No startup
 * work is added: initialize only after the successful HAL pipe-stop. */
#define SHUTDOWN ((volatile uint32_t *)0x343F8900U)
static void fast_shutdown_data_off(void)
{
  for(unsigned i=0;i<16U;++i) SHUTDOWN[i]=0;
  SHUTDOWN[0]=0x46534431U; /* FSD1 */
  SHUTDOWN[1]=1U; SHUTDOWN[2]=1U;
  SHUTDOWN[3]=RCC->APB5ENR; SHUTDOWN[4]=RCC->DIVENR; SHUTDOWN[5]=RCC->APB5RSTR;
  const uint32_t clocks=RCC_APB5ENR_CSIEN|RCC_APB5ENR_DCMIPPEN;
  const uint32_t kernels=RCC_DIVENR_IC18EN|RCC_DIVENR_IC17EN;
  const uint32_t resets=RCC_APB5RSTR_CSIRST|RCC_APB5RSTR_DCMIPPRST;
  if((SHUTDOWN[3]&clocks)!=clocks || (SHUTDOWN[4]&kernels)!=kernels || (SHUTDOWN[5]&resets)) {
    SHUTDOWN[15]=(uint32_t)-1; fail(0xA5,-1);
  }
  SHUTDOWN[2]=2U;
  /* All peripheral reads follow the RCC clock/reset guards above. */
  SHUTDOWN[6]=CSI->SR0; SHUTDOWN[7]=DCMIPP->P0FCTCR;
  SHUTDOWN[8]=DCMIPP->CMSR1; SHUTDOWN[9]=DCMIPP->P0FSCR;
  SHUTDOWN[10]=CSI->PRCR; SHUTDOWN[11]=CSI->PCR;
  /* RM0486: VC0STATEF bit17, CPTREQ bit3, P0CPTACT bit15, PIPEN bit31. */
  if((SHUTDOWN[6]&CSI_SR0_VC0STATEF) || (SHUTDOWN[7]&DCMIPP_P0FCTCR_CPTREQ) ||
     (SHUTDOWN[8]&DCMIPP_CMSR1_P0CPTACT) || (SHUTDOWN[9]&DCMIPP_P0FSCR_PIPEN)) {
    SHUTDOWN[15]=(uint32_t)-2; fail(0xA5,-2);
  }
  if(!(SHUTDOWN[10]&CSI_PRCR_PEN) || SHUTDOWN[11]!=0x0FU) {
    SHUTDOWN[15]=(uint32_t)-3; fail(0xA5,-3);
  }
  SHUTDOWN[2]=3U;
  event(442); fast_snapshot(442);
  SHUTDOWN[13]=DWT->CYCCNT;
  /* Preserve clock module, PHY power, PEN, interrupt enables and error flags. */
  CLEAR_BIT(CSI->PCR,CSI_PCR_DL0EN|CSI_PCR_DL1EN); __DSB();
  SHUTDOWN[12]=CSI->PCR; SHUTDOWN[14]=DWT->CYCCNT;
  event(443); fast_snapshot(443);
  if(SHUTDOWN[12]!=0x03U) { SHUTDOWN[15]=(uint32_t)-4; fail(0xA5,-4); }
  SHUTDOWN[2]=4U; __DMB();
}
#endif

__attribute__((noreturn,noinline,used)) void fast_failure_park(void)
{
  __disable_irq(); __DSB(); __ISB();
  __asm volatile(".global fast_failure_idle\n"
                 "fast_failure_idle:\n"
                 "b.n .\n");
  __builtin_unreachable();
}

__attribute__((noreturn)) static void fast_failure_quiesce(uint32_t where,int32_t result)
{
  __disable_irq(); FAST[16]=where; FAST[17]=(uint32_t)result;
  fast_snapshot(0xF0000000U|where);
  FAST[25]=RCC->APB5ENR;
  if((FAST[25]&RCC_APB5ENR_DCMIPPEN) &&
     !(RCC->APB5RSTR&RCC_APB5RSTR_DCMIPPRST) && (RCC->DIVENR&RCC_DIVENR_IC17EN)) {
    FAST[26]=DCMIPP->P0FCTCR; FAST[27]=DCMIPP->CMSR2;
  }
  FAST[28]=RCC->APB5RSTR;
  RCC->APB5RSTSR=RCC_APB5RSTSR_DCMIPPRSTS; __DSB();
  FAST[29]=RCC->APB5RSTR; FAST[18]=__get_PRIMASK();
  FAST[19]=((FAST[29]&RCC_APB5RSTR_DCMIPPRST) && FAST[18]==1U)?0x51554945U:0U;
  __DSB(); __ISB(); fast_failure_park();
}

__attribute__((noreturn)) static void fail(uint32_t where, int32_t result)
{
  __disable_irq();
  status_led_proof_phase(STATUS_LED_ERROR,LED_P_ERROR_CYCLE);
  TRACE[3] = (uint32_t)result;
  TRACE[4] = hcam.ErrorCode;
  event(0x80000000U | where);
  fast_failure_quiesce(where,result);
}
static void check(uint32_t where, int result) { if (result) fail(where, result); }
void SysTick_Handler(void) { HAL_IncTick(); }
void DCMIPP_IRQHandler(void) { HAL_DCMIPP_IRQHandler(&hcam); }
void CSI_IRQHandler(void) { irq_sr0=CSI->SR0; irq_sr1=CSI->SR1; irq_ier0=CSI->IER0; irq_ier1=CSI->IER1; fast_snapshot(420); HAL_DCMIPP_CSI_IRQHandler(&hcam); }
void EXTI0_IRQHandler(void) { HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_0); }
void HAL_GPIO_EXTI_Rising_Callback(uint16_t pin)
{
  if(pin==GPIO_PIN_0) {
    fast_strobes++; event(50);
    /* Preserve the original timing marker; only the FIRST exposure changes LEDs. */
    if(fast_strobes==1U) status_led_proof_phase(STATUS_LED_ACQUIRE,LED_P_BLUE_CYCLE);
  }
}
void HAL_GPIO_EXTI_Falling_Callback(uint16_t pin) { if(pin==GPIO_PIN_0) event(51); }
void HardFault_Handler(void) {
  status_led_set(STATUS_LED_ERROR);
  TRACE[24] = SCB->CFSR; TRACE[25] = SCB->HFSR;
  TRACE[26] = SCB->BFAR; TRACE[27] = SCB->MMFAR;
  TRACE[1] = 0xFFFFFFFF;
  for (;;) __NOP();
}
void assert_failed(uint8_t *file, uint32_t line) { (void)file; fail(0x7FFF, line); }

void HAL_DCMIPP_MspInit(DCMIPP_HandleTypeDef *handle)
{
  (void)handle;
  __HAL_RCC_DCMIPP_CLK_ENABLE();
  __HAL_RCC_DCMIPP_FORCE_RESET(); __HAL_RCC_DCMIPP_RELEASE_RESET();
  __HAL_RCC_CSI_CLK_ENABLE();
  __HAL_RCC_CSI_FORCE_RESET(); __HAL_RCC_CSI_RELEASE_RESET();
  HAL_NVIC_SetPriority(DCMIPP_IRQn, 7, 0); HAL_NVIC_EnableIRQ(DCMIPP_IRQn);
  HAL_NVIC_SetPriority(CSI_IRQn, 7, 0); HAL_NVIC_EnableIRQ(CSI_IRQn);
}
void HAL_DCMIPP_PIPE_FrameEventCallback(DCMIPP_HandleTypeDef *h, uint32_t pipe)
{
  (void)h;
  if(pipe==0) {
    frames++; event(30);
    if(frames==1U) {
      FAST[31]=fast_strobes;
      status_led_proof_phase(STATUS_LED_OFF,LED_P_OFF_CYCLE);
    }
    fast_snapshot(430);
  }
}
void HAL_DCMIPP_PIPE_VsyncEventCallback(DCMIPP_HandleTypeDef *h, uint32_t pipe)
{ (void)h; if (pipe == 0) { vsyncs++; event(29); if(vsyncs==1U) FAST[30]=fast_strobes; fast_snapshot(429); } }
static void error_event(uint32_t id,DCMIPP_HandleTypeDef *h)
{
  uint32_t n=TRACE[36];
  if(n<16) {
    volatile uint32_t *r=(volatile uint32_t *)0x343F1000U+n*12;
    r[0]=id; r[1]=DWT->CYCCNT; r[2]=HAL_GetTick(); r[3]=h->ErrorCode;
    r[4]=irq_sr0; r[5]=irq_sr1; r[6]=h->Instance->CMSR2; r[7]=TRACE[1];
    r[8]=irq_ier0; r[9]=irq_ier1; r[10]=CSI->IER0; r[11]=CSI->IER1;
    TRACE[36]=n+1;
    TRACE[38]=12;
  }
  errors++; TRACE[4] |= h->ErrorCode; event(id);
}
void HAL_DCMIPP_PIPE_ErrorCallback(DCMIPP_HandleTypeDef *h, uint32_t pipe)
{ (void)pipe; error_event(70,h); }
void HAL_DCMIPP_ErrorCallback(DCMIPP_HandleTypeDef *h)
{ error_event(71,h); }
void HAL_DCMIPP_CSI_LineErrorCallback(DCMIPP_HandleTypeDef *h, uint32_t lane)
{ error_event(72+lane,h); }

static void shutdown_pin(VD6G_Ctx_t *ctx, int value)
{ (void)ctx; HAL_GPIO_WritePin(GPIOO, GPIO_PIN_5, value ? GPIO_PIN_SET : GPIO_PIN_RESET); event(value ? 11 : 10); }
static int rd8(VD6G_Ctx_t *ctx, uint16_t a, uint8_t *v)
{ (void)ctx; read_transactions++; read_bytes++; return BSP_I2C2_ReadReg16(0x20, a, v, 1); }
static int rd16(VD6G_Ctx_t *ctx, uint16_t a, uint16_t *v)
{ (void)ctx; read_transactions++; read_bytes+=2; return BSP_I2C2_ReadReg16(0x20, a, (uint8_t*)v, 2); }
static int rd32(VD6G_Ctx_t *ctx, uint16_t a, uint32_t *v)
{ (void)ctx; read_transactions++; read_bytes+=4; return BSP_I2C2_ReadReg16(0x20, a, (uint8_t*)v, 4); }
static int wr8(VD6G_Ctx_t *ctx, uint16_t a, uint8_t v)
{
  (void)ctx;
  write_transactions++; write_bytes++;
  if (a == 0x0201 && v == 1) event(24);
  int r = BSP_I2C2_WriteReg16(0x20, a, &v, 1);
  if (a == 0x0201 && v == 1) {
    event(25);
    TRACE[40]=write_transactions; TRACE[41]=write_bytes;
    TRACE[42]=read_transactions; TRACE[43]=read_bytes;
  }
  return r;
}
static int wr16(VD6G_Ctx_t *ctx, uint16_t a, uint16_t v)
{ (void)ctx; write_transactions++; write_bytes+=2; return BSP_I2C2_WriteReg16(0x20, a, (uint8_t*)&v, 2); }
static int wr32(VD6G_Ctx_t *ctx, uint16_t a, uint32_t v)
{ (void)ctx; write_transactions++; write_bytes+=4; return BSP_I2C2_WriteReg16(0x20, a, (uint8_t*)&v, 4); }
static int wrarray(VD6G_Ctx_t *ctx, uint16_t a, uint8_t *data, int len)
{
  (void)ctx;
  while (len) {
    int n = len > 128 ? 128 : len;
    write_transactions++; write_bytes+=n;
    int r = BSP_I2C2_WriteReg16(0x20, a, data, n);
    if (r) return r;
    a += n; data += n; len -= n;
  }
  return 0;
}
static void delay(VD6G_Ctx_t *ctx, uint32_t ms) { (void)ctx; HAL_Delay(ms); }
void bench_delay_us(uint32_t us)
{
  uint32_t ticks=(SystemCoreClock/1000000U)*us;
  uint32_t start=DWT->CYCCNT;
  while((uint32_t)(DWT->CYCCNT-start)<ticks) __NOP();
}
static void log_none(VD6G_Ctx_t *ctx, int level, const char *format, va_list ap)
{ (void)ctx; (void)level; (void)format; (void)ap; }

static void prepare_receiver(void)
{
  hcam.Instance=DCMIPP;
  check(16, MX_DCMIPP_ClockConfig(&hcam));
  check(17, HAL_DCMIPP_Init(&hcam));
  DCMIPP_CSI_ConfTypeDef csi={ .NumberOfLanes=DCMIPP_CSI_TWO_DATA_LANES,
    .DataLaneMapping=DCMIPP_CSI_PHYSICAL_DATA_LANES, .PHYBitrate=DCMIPP_CSI_PHY_BT_800 };
  check(18, HAL_DCMIPP_CSI_SetConfig(&hcam,&csi));
  __HAL_DCMIPP_CSI_ENABLE_IT(CSI,DCMIPP_CSI_IT_CRCERR | DCMIPP_CSI_IT_ECCERR | DCMIPP_CSI_IT_CECCERR);
  check(19, HAL_DCMIPP_CSI_SetVCConfig(&hcam,DCMIPP_VIRTUAL_CHANNEL0,DCMIPP_CSI_DT_BPP10));
  DCMIPP_CSI_PIPE_ConfTypeDef pcsi={ .DataTypeMode=DCMIPP_DTMODE_DTIDA, .DataTypeIDA=DCMIPP_DT_RAW10 };
  check(20, HAL_DCMIPP_CSI_PIPE_SetConfig(&hcam,DCMIPP_PIPE0,&pcsi));
  DCMIPP_PipeConfTypeDef pipe={ .FrameRate=DCMIPP_FRAME_RATE_ALL };
  check(21, HAL_DCMIPP_PIPE_SetConfig(&hcam,DCMIPP_PIPE0,&pipe));
  /* Avoid full-buffer CPU initialization before first exposure. No D-cache is
   * enabled; fixed RAM region is written only by the snapshot DMA. */
  /* RM0486: RAW10 expands to16-bit right-aligned words. */
  CLEAR_BIT(DCMIPP->P0PPCR, DCMIPP_P0PPCR_PAD);
  check(0x80,HAL_DCMIPP_PIPE_EnableLimitEvent(&hcam,DCMIPP_PIPE0,BYTES/4U));
  volatile uint32_t *guard=(volatile uint32_t *)(0x34000000U+BYTES);
  for(unsigned i=0;i<8;++i) guard[i]=0xA15A1000U+i;
  __DSB();
  event(21);
}

static void arm_receiver(void)
{
  check(22, HAL_DCMIPP_CSI_PIPE_Start(&hcam,DCMIPP_PIPE0,DCMIPP_VIRTUAL_CHANNEL0,(uint32_t)g_frame,DCMIPP_MODE_SNAPSHOT));
  event(22); fast_snapshot(422);
}

int main(void)
{
  fast_init();
  event(2);
  if(BENCH_STOP_STAGE==2) for(;;) __NOP();
  /* Match the proven SRAM capture's initial clock transition. UART, USB,
   * FreeRTOS and external-memory initialization are deliberately absent. */
  if(BENCH_ROM_CLOCKS) SystemCoreClockUpdate();
  else {
    __HAL_RCC_CPUCLK_CONFIG(RCC_CPUCLKSOURCE_HSI);
    __HAL_RCC_SYSCLK_CONFIG(RCC_SYSCLKSOURCE_HSI);
    SystemCoreClock = HSI_VALUE;
  }
  HAL_Init();
  __enable_irq();
  SCB_EnableICache();
  if(!BENCH_ROM_CLOCKS) baseline_clocks();
  event(3);
  if(BENCH_STOP_STAGE==3) for(;;) __NOP();
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_RCC_RIFSC_CLK_ENABLE();
  RIMC_MasterConfig_t master = { .MasterCID = RIF_CID_1, .SecPriv = RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_PRIV };
  HAL_RIF_RIMC_ConfigMasterAttributes(RIF_MASTER_INDEX_DCMIPP, &master);
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_CSI, RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_PRIV);
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_DCMIPP, RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_PRIV);
  event(4);
  HAL_PWREx_EnableVddIO2();
  __HAL_RCC_GPIOO_CLK_ENABLE(); __HAL_RCC_GPIOA_CLK_ENABLE();
  GPIO_InitTypeDef gpio = { .Pin=GPIO_PIN_5, .Mode=GPIO_MODE_OUTPUT_PP, .Pull=GPIO_NOPULL, .Speed=GPIO_SPEED_FREQ_VERY_HIGH };
  HAL_GPIO_Init(GPIOO, &gpio);
  gpio.Pin=GPIO_PIN_0; gpio.Mode=GPIO_MODE_INPUT; HAL_GPIO_Init(GPIOA, &gpio);
  check(5, BSP_I2C2_Init());
  if(BUS_I2C2_FREQUENCY>400000U) {
    extern I2C_HandleTypeDef hbus_i2c2;
    check(0x50,HAL_I2CEx_ConfigFastModePlus(&hbus_i2c2,I2C_FASTMODEPLUS_ENABLE));
  }
  TRACE[32]=HAL_RCC_GetPCLK1Freq(); TRACE[33]=I2C2->TIMINGR; TRACE[34]=I2C2->CR1;
  event(5);
  sensor.shutdown_pin=shutdown_pin; sensor.read8=rd8; sensor.read16=rd16; sensor.read32=rd32;
  sensor.write8=wr8; sensor.write16=wr16; sensor.write32=wr32; sensor.write_array=wrarray;
  sensor.delay=delay; sensor.log=log_none;
  /* Receiver-only handoff. Stage1 has already completed START's I2C write.
   * This deadline is intentionally earlier than the measured first STROBE;
   * a miss aborts the experiment and never claims a first-frame capture. */
  volatile uint32_t *early_sensor=(volatile uint32_t *)0x343F4000U;
  if(early_sensor[0]!=0x53454E31U || early_sensor[1]!=37U || early_sensor[2]) fail(0x71,-1);
  uint32_t sensor_start_end=early_sensor[5];
  TRACE[62]=(uint32_t)(DWT->CYCCNT-sensor_start_end); TRACE[63]=1800000U;
  if(TRACE[62]>=1800000U) fail(0x72,-1);
  gpio.Pin=GPIO_PIN_0; gpio.Mode=GPIO_MODE_IT_RISING_FALLING; gpio.Pull=GPIO_NOPULL;
  HAL_GPIO_Init(GPIOA,&gpio);
  __HAL_GPIO_EXTI_CLEAR_RISING_IT(GPIO_PIN_0); __HAL_GPIO_EXTI_CLEAR_FALLING_IT(GPIO_PIN_0);
  TRACE[35]=HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_0);
  if(TRACE[35]) fail(0x73,-1);
  HAL_NVIC_SetPriority(EXTI0_IRQn,3,0); HAL_NVIC_EnableIRQ(EXTI0_IRQn);
  TRACE[30]=2;
  prepare_receiver();
  early_sensor[16]=DWT->CYCCNT;
  TRACE[61]=(uint32_t)(early_sensor[16]-sensor_start_end);
  if(TRACE[61]>=1800000U) {
    /* Configuration missed budget; VC capture has not been armed. */
    (void)wr8(&sensor,0x0202,1); /* Request stop; recorded failure remains authoritative. */
    fail(0x74,-1);
  }
  event(250);
  fast_streaming_data_enable();
  ready_force_before_stop();
  fast_qualify_stop();
  ready_force_release();
  if(frames || vsyncs) fail(0xA4,-1);
  FAST[22]=DWT->CYCCNT; FAST[23]=fast_strobes; FAST[24]=GPIOA->IDR&1U;
  event(441); fast_snapshot(441);
  arm_receiver();
  uint8_t state=0xFF; uint32_t ack_started=HAL_GetTick();
  do { check(0x75,rd8(&sensor,0x0201,&state)); if(HAL_GetTick()-ack_started>500U) fail(0x75,-100); } while(state);
  FAST[9]=DWT->CYCCNT; event(425); fast_snapshot(425);
  do { check(0x76,rd8(&sensor,0x0028,&state)); if(HAL_GetTick()-ack_started>500U) fail(0x76,-100); } while(state!=3U);
  sensor.ctx.is_streaming=1;
  TRACE[28]=TRACE[35]; TRACE[29]=HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_0);
  FAST[10]=DWT->CYCCNT; event(26); fast_snapshot(426);
  uint32_t start=HAL_GetTick();
  while (!frames) if (HAL_GetTick()-start > 2000) fail(28,-100);
  event(31); fast_snapshot(431);
  TRACE[44]=CSI->SR0; TRACE[45]=CSI->SR1;
  volatile uint32_t *raw10=(volatile uint32_t *)0x343F6000U;
  raw10[0]=0x52313046U; raw10[1]=DCMIPP->P0DCCNTR;
  raw10[2]=DCMIPP->P0PPCR; raw10[3]=DCMIPP->P0DCLMTR;
  raw10[4]=CSI->VC0CFGR1; raw10[5]=DCMIPP->P0FSCR;
  raw10[6]=DCMIPP->CMSR2; raw10[7]=0;
  volatile uint32_t *guard=(volatile uint32_t *)(0x34000000U+BYTES);
  for(unsigned i=0;i<8;++i) if(guard[i]!=(0xA15A1000U+i)) raw10[7]|=1U<<i;
  if(raw10[1]!=BYTES || raw10[7]) fail(0x81,-1);

  uint16_t coarse=0,line_length=0;
  check(0x53,rd16(&sensor,0x0064,&coarse)); TRACE[46]=coarse;
  check(0x54,rd16(&sensor,0x0300,&line_length)); TRACE[47]=line_length;
  /* Read-only checks deferred until the first frame is safely in RAM. */
  early_sensor[11]=line_length;
  if(line_length!=1236U) fail(0x7D,-1);
  uint16_t sensor_rom=0;
  check(0x7E,rd16(&sensor,0x0014,&sensor_rom)); early_sensor[10]=sensor_rom;
  uint8_t sensor_orientation=0;
  check(0x7F,rd8(&sensor,0x001A,&sensor_orientation)); early_sensor[17]=sensor_orientation;

  /* BENCH_CLOCK_DIAGNOSTICS: after first frame, before stream stop. */
  uint32_t clock_value;
  for(unsigned i=0;i<4;++i) { check(0x60+i,rd32(&sensor,0x0034+i*4,&clock_value)); TRACE[52+i]=clock_value; }
  check(0x64,rd32(&sensor,0x0044,&clock_value)); TRACE[56]=clock_value;
  uint8_t clock_byte;
  check(0x65,rd8(&sensor,0x0048,&clock_byte)); TRACE[57]=clock_byte;
  check(0x66,rd16(&sensor,0x0458,&coarse)); TRACE[58]=coarse;
  uint8_t raw_bits=0,raw_dt=0;
  check(0x82,rd8(&sensor,0x030A,&raw_bits));
  check(0x83,rd8(&sensor,0x030F,&raw_dt));
  raw10[8]=raw_bits; raw10[9]=raw_dt;
  if(raw_bits!=10U || raw_dt!=0x2BU) fail(0x84,-1);


  /* Snapshot stops DMA after the complete first frame; sensor stream can be
   * stopped now, without changing the already frozen capture. */
  fast_snapshot(435);
  check(32, HAL_DCMIPP_CSI_PIPE_Stop(&hcam,DCMIPP_PIPE0,DCMIPP_VIRTUAL_CHANNEL0));
  fast_snapshot(439);
#if FAST_SHUTDOWN_DATA_OFF
  fast_shutdown_data_off();
#endif
  check(33, VD6G_Stop(&sensor));
  fast_snapshot(436);
  __DSB();
  uint32_t min=255,max=0,sum=0,hash=2166136261U;
  for (unsigned i=0;i<BYTES;++i) { uint32_t v=g_frame[i]; if(v<min)min=v; if(v>max)max=v; sum+=v; hash=(hash^v)*16777619U; }
  TRACE[5]=frames; TRACE[6]=vsyncs; TRACE[7]=errors; TRACE[8]=min; TRACE[9]=max; TRACE[10]=sum; TRACE[11]=hash;
  TRACE[12]=(uint32_t)g_frame; TRACE[13]=BYTES; TRACE[14]=WIDTH; TRACE[15]=HEIGHT;
  TRACE[4] |= hcam.ErrorCode;
  fast_snapshot(440); if(FAST[3]) fail(0xA2,-1); FAST[1]=40;
  event(40);
  status_led_complete_sleep();
}
