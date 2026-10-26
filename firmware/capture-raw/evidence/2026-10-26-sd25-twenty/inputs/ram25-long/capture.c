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
#include "phase_gpio.h"
#include "capture_profile.h"
#define CPROF ((volatile uint32_t *)CAPTURE_PROFILE_ADDRESS)
extern void status_led_complete_sleep(void) __attribute__((noreturn));

#define WIDTH 1120U
#define HEIGHT 1364U
#define BYTES (WIDTH * HEIGHT * 5U / 4U)
#include "runtime.h"
#include "cycle_trace.h"
#include "producer.h"
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
__attribute__((section(".psram_bss"),aligned(32))) uint8_t raw_frame_allocation[4U+MAGIC_SLOTS_PADDED_BYTES+32U];
#define g_frame (raw_frame_allocation+160U)
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
static int fast_shutdown_data_off(void)
{
  for(unsigned i=0;i<16U;++i) SHUTDOWN[i]=0;
  SHUTDOWN[0]=0x46534431U; /* FSD1 */
  SHUTDOWN[1]=1U; SHUTDOWN[2]=1U;
  SHUTDOWN[3]=RCC->APB5ENR; SHUTDOWN[4]=RCC->DIVENR; SHUTDOWN[5]=RCC->APB5RSTR;
  const uint32_t clocks=RCC_APB5ENR_CSIEN|RCC_APB5ENR_DCMIPPEN;
  const uint32_t kernels=RCC_DIVENR_IC18EN|RCC_DIVENR_IC17EN;
  const uint32_t resets=RCC_APB5RSTR_CSIRST|RCC_APB5RSTR_DCMIPPRST;
  if((SHUTDOWN[3]&clocks)!=clocks || (SHUTDOWN[4]&kernels)!=kernels || (SHUTDOWN[5]&resets)) {
    SHUTDOWN[15]=(uint32_t)-1; return -1;
  }
  SHUTDOWN[2]=2U;
  /* All peripheral reads follow the RCC clock/reset guards above. */
  SHUTDOWN[6]=CSI->SR0; SHUTDOWN[7]=DCMIPP->P0FCTCR;
  SHUTDOWN[8]=DCMIPP->CMSR1; SHUTDOWN[9]=DCMIPP->P0FSCR;
  SHUTDOWN[10]=CSI->PRCR; SHUTDOWN[11]=CSI->PCR;
  /* RM0486: VC0STATEF bit17, CPTREQ bit3, P0CPTACT bit15, PIPEN bit31. */
  if((SHUTDOWN[6]&CSI_SR0_VC0STATEF) || (SHUTDOWN[7]&DCMIPP_P0FCTCR_CPTREQ) ||
     (SHUTDOWN[8]&DCMIPP_CMSR1_P0CPTACT) || (SHUTDOWN[9]&DCMIPP_P0FSCR_PIPEN)) {
    SHUTDOWN[15]=(uint32_t)-2; return -2;
  }
  if(!(SHUTDOWN[10]&CSI_PRCR_PEN) || SHUTDOWN[11]!=0x0FU) {
    SHUTDOWN[15]=(uint32_t)-3; return -3;
  }
  SHUTDOWN[2]=3U;
  event(442); fast_snapshot(442);
  SHUTDOWN[13]=DWT->CYCCNT;
  /* Preserve clock module, PHY power, PEN, interrupt enables and error flags. */
  CLEAR_BIT(CSI->PCR,CSI_PCR_DL0EN|CSI_PCR_DL1EN); __DSB();
  SHUTDOWN[12]=CSI->PCR; SHUTDOWN[14]=DWT->CYCCNT;
  event(443); fast_snapshot(443);
  if(SHUTDOWN[12]!=0x03U) { SHUTDOWN[15]=(uint32_t)-4; return -4; }
  SHUTDOWN[2]=4U; __DMB(); return 0;
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
  status_led_proof_phase(STATUS_LED_ERROR,LED_P_ERROR_CYCLE);
  TRACE[3] = (uint32_t)result;
  TRACE[4] = hcam.ErrorCode;
  event(0x80000000U | where);
  raw_capture_fail(where,result);
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
    if(fast_strobes==1U) {
      status_led_proof_phase(STATUS_LED_ACQUIRE,LED_P_BLUE_CYCLE);
      (void)phase_gpio_emit(2U);
    }
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
#if RAW_LINE_SNAPSHOTS
static void raw_line_snapshot(uint32_t index,uint32_t offset,uint32_t bytes)
{
  /* Copy the newest published tail immediately, before publication. A later
   * slow SD read can hide an early-memory-visibility error; this snapshot cannot.
   * Diagnostic RAM mode only. The source has no dirty CPU cache alias. */
  volatile const uint32_t *src=(volatile const uint32_t *)(RAW_FRAME_ADDRESS+offset);
  volatile uint32_t *dst=(volatile uint32_t *)(RAW_PRODUCER_SNAPSHOT_ADDRESS+index*512U);
  for(uint32_t i=0;i<bytes/4U;i++) dst[i]=src[i];
  __DMB();
}
#endif
void HAL_DCMIPP_PIPE_LineEventCallback(DCMIPP_HandleTypeDef *h,uint32_t pipe)
{
  (void)h;
#if RAW_LINE_STREAM
  if(pipe==0U) {
    if(errors || hcam.ErrorCode) raw_producer_fault(&raw_producer,RAW_PRODUCER_ERR_CAPTURE);
    raw_producer_line(&raw_producer,DWT->CYCCNT,
#if RAW_LINE_SNAPSHOTS
      raw_line_snapshot
#else
      0
#endif
    );
  }
#else
  (void)pipe;
#endif
}

void HAL_DCMIPP_PIPE_FrameEventCallback(DCMIPP_HandleTypeDef *h, uint32_t pipe)
{
  (void)h;
  if(pipe==0) {
    CYCLE_MARK(FRAME_IRQ);
    frames++;
#if RAW_LINE_STREAM
    raw_producer_frame(&raw_producer,DWT->CYCCNT);
#endif
    raw_capture_frame_event(); event(30);
    if(frames==1U) {
      FAST[31]=fast_strobes;
      (void)phase_gpio_emit(3U);
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
#if RAW_LINE_STREAM
  raw_producer_fault(&raw_producer,RAW_PRODUCER_ERR_CAPTURE);
#endif
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
  check(19, HAL_DCMIPP_CSI_SetVCConfig(&hcam,DCMIPP_VIRTUAL_CHANNEL0,DCMIPP_CSI_DT_BPP8));
  DCMIPP_CSI_PIPE_ConfTypeDef pcsi={ .DataTypeMode=DCMIPP_DTMODE_DTIDA, .DataTypeIDA=0x30U };
  check(20, HAL_DCMIPP_CSI_PIPE_SetConfig(&hcam,DCMIPP_PIPE0,&pcsi));
  DCMIPP_PipeConfTypeDef pipe={ .FrameRate=DCMIPP_FRAME_RATE_ALL };
  check(21, HAL_DCMIPP_PIPE_SetConfig(&hcam,DCMIPP_PIPE0,&pipe));
  /* Avoid full-buffer CPU initialization before first exposure. No D-cache is
   * enabled; fixed RAM region is written only by the snapshot DMA. */
  /* RM0486: RAW10 expands to16-bit right-aligned words. */
  CLEAR_BIT(DCMIPP->P0PPCR, DCMIPP_P0PPCR_PAD);
  check(0x80,HAL_DCMIPP_PIPE_EnableLimitEvent(&hcam,DCMIPP_PIPE0,BYTES/4U));
  volatile uint32_t *guard=(volatile uint32_t *)(RAW_FRAME_ADDRESS+BYTES);
  for(unsigned i=0;i<8;++i) guard[i]=0xA15A1000U+i;
#if RAW_MAGIC_FORMAT
  *(volatile uint32_t *)RAW_SLOT_BUFFER_ADDRESS=MAGIC_SLOTS_START_MAGIC;
  volatile uint32_t *metadata=(volatile uint32_t *)(RAW_SLOT_BUFFER_ADDRESS+MAGIC_SLOTS_METADATA_OFFSET);
  for(unsigned i=0;i<MAGIC_SLOTS_METADATA_BYTES/4U;++i) metadata[i]=0;
  volatile uint32_t *pad_guard=(volatile uint32_t *)(RAW_SLOT_BUFFER_ADDRESS+MAGIC_SLOTS_PADDED_BYTES);
  for(unsigned i=0;i<8;++i) pad_guard[i]=0xA15A1000U+i+1U;
#endif
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
  raw_runtime_dispatch();
  fast_init();
  check(0xD0,!phase_gpio_init());
  (void)phase_gpio_emit(1U);
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
  CYCLE_MARK(HAL_BEGIN);
  HAL_Init();
  CYCLE_MARK(HAL_DONE);
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
  CYCLE_MARK(I2C_BEGIN);
  check(5, BSP_I2C2_Init());
  CYCLE_MARK(I2C_DONE);
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
  CYCLE_MARK(RECEIVER_PREPARE_BEGIN);
  prepare_receiver();
  CYCLE_MARK(RECEIVER_PREPARE_DONE);
  early_sensor[16]=DWT->CYCCNT;
  TRACE[61]=(uint32_t)(early_sensor[16]-sensor_start_end);
  if(TRACE[61]>=1800000U) {
    /* Configuration missed budget; VC capture has not been armed. */
    (void)wr8(&sensor,0x0202,1); /* Request stop; recorded failure remains authoritative. */
    fail(0x74,-1);
  }
  event(250);
  CYCLE_MARK(PHY_ENABLE_BEGIN);
  fast_streaming_data_enable();
  ready_force_before_stop();
  CYCLE_MARK(PHY_STOP_QUALIFY_BEGIN);
  fast_qualify_stop();
  CYCLE_MARK(PHY_STOP_QUALIFY_DONE);
  ready_force_release();
  if(frames || vsyncs) fail(0xA4,-1);
  FAST[22]=DWT->CYCCNT; FAST[23]=fast_strobes; FAST[24]=GPIOA->IDR&1U;
  event(441); fast_snapshot(441);
#if RAW_LINE_STREAM
  /* HAL enable does not clear stale LINE status. Before arming, discard only
   * this flag so event1 cannot consume the holdback without64 captured lines. */
  DCMIPP->CMFCR=DCMIPP_CMFCR_CP0LINEF; __DSB();
  check(0x8E,HAL_DCMIPP_PIPE_EnableLineEvent(&hcam,DCMIPP_PIPE0,DCMIPP_MULTILINE_64_LINES));
#endif
  CYCLE_MARK(RECEIVER_ARM_BEGIN);
  arm_receiver();
  CYCLE_MARK(RECEIVER_ARM_DONE);
  raw_capture_armed();
  CYCLE_MARK(START_ACK_BEGIN);
  uint8_t state=0xFF; uint32_t ack_started=HAL_GetTick();
  do { CYCLE_COUNT(START_ACK_READS); check(0x75,rd8(&sensor,0x0201,&state)); if(HAL_GetTick()-ack_started>500U) fail(0x75,-100); } while(state);
  CYCLE_MARK(START_ACK_DONE);
  FAST[9]=DWT->CYCCNT; event(425); fast_snapshot(425);
  do { CYCLE_COUNT(STREAMING_STATE_READS); check(0x76,rd8(&sensor,0x0028,&state)); if(HAL_GetTick()-ack_started>500U) fail(0x76,-100); } while(state!=3U);
  CYCLE_MARK(STREAMING_OBSERVED);
  sensor.ctx.is_streaming=1;
  TRACE[28]=TRACE[35]; TRACE[29]=HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_0);
  FAST[10]=DWT->CYCCNT; event(26); fast_snapshot(426);
  raw_storage_execute();
}

static uint32_t capture_finalizing,capture_ready,capture_sensor_stopped,capture_exposure_us,capture_async_error;
#if RAW_ASYNC_STOP
static uint32_t capture_stop_started,capture_stop_pending,capture_stop_poll;
#endif
uint32_t raw_capture_available(void)
{
#if RAW_LINE_STREAM
  return raw_producer_available(&raw_producer);
#else
  return capture_ready?BYTES:0U;
#endif
}
uint32_t raw_capture_frame_validated(void) { return capture_ready; }
uint32_t raw_capture_fault(void) { return errors|hcam.ErrorCode|capture_async_error|raw_producer.error; }
uint32_t raw_capture_sensor_stopped(void) { return capture_sensor_stopped; }
uint32_t raw_capture_exposure_us(void) { return capture_exposure_us; }
#define MAGIC_FAIL(where,result) do { capture_async_error=(where); \
  raw_producer_fault(&raw_producer,RAW_PRODUCER_ERR_CAPTURE); return; } while(0)
#define MAGIC_CHECK(where,call) do { int magic_result=(call); \
  if(magic_result) MAGIC_FAIL(where,magic_result); } while(0)
void raw_capture_poll(void)
{
  /* The full post-frame checks can terminate on failure. They must never run
   * while SD owns an active command/DMA buffer. The already-started async STOP
   * poll below has deferred errors and is safe after capture_finalizing. */
  /* Magic streaming uses returning errors below; the SD owner aborts
   * and proves media idle before failure cleanup. Never park here. */
  if(capture_async_error || raw_producer.error) return;
#if RAW_ASYNC_STOP
  if(capture_stop_pending) {
    uint32_t now=DWT->CYCCNT;
    if((uint32_t)(now-capture_stop_started)>400000000U) { capture_async_error=0x8BU; capture_stop_pending=0; return; }
    if((uint32_t)(now-capture_stop_poll)<400000U) return;
    capture_stop_poll=now;
    CYCLE_COUNT(SENSOR_STOP_POLLS);
    uint8_t ack=0xFF,state=0xFF;
    if(rd8(&sensor,0x0202,&ack)) { capture_async_error=0x8CU; capture_stop_pending=0; return; }
    if(ack) return;
    if(rd8(&sensor,0x0028,&state)) { capture_async_error=0x8DU; capture_stop_pending=0; return; }
    if(state!=2U) return;
    sensor.ctx.is_streaming=0; capture_stop_pending=0; capture_sensor_stopped=1;
    CPROF[CP_SENSOR_STOP_DONE]=DWT->CYCCNT; CPROF[CP_FLAGS]|=CP_F_SAFE_STOP;
    CYCLE_MARK(SENSOR_STOP_ACK_DONE);
    raw_capture_stopped(); return;
  }
#endif
  if(!frames || capture_finalizing || capture_ready) return;
  CYCLE_MARK(FRAME_CHECK_BEGIN);
  capture_finalizing=1U;
  volatile uint32_t *early_sensor=(volatile uint32_t *)0x343F4000U;
  event(31); fast_snapshot(431);
  uint32_t profile_started=DWT->CYCCNT;
  for(unsigned i=0;i<CAPTURE_PROFILE_WORDS;++i) CPROF[i]=0U;
  CPROF[CP_MAGIC]=CAPTURE_PROFILE_MAGIC;
  CPROF[CP_SCHEMA]=CAPTURE_PROFILE_SCHEMA; CPROF[CP_WORDS]=CAPTURE_PROFILE_WORDS;
  CPROF[CP_PROFILE]=CAPTURE_DIAGNOSTICS; CPROF[CP_STATE]=1U;
  CPROF[CP_POST_FRAME_BEGIN]=profile_started;
  CPROF[CP_FRAME]=(uint32_t)g_frame; CPROF[CP_BYTES]=BYTES;
  CPROF[CP_WIDTH]=WIDTH; CPROF[CP_HEIGHT]=HEIGHT;
  TRACE[44]=CSI->SR0; TRACE[45]=CSI->SR1;
  volatile uint32_t *raw10=(volatile uint32_t *)0x343F6000U;
  raw10[0]=0x52313046U; raw10[1]=DCMIPP->P0DCCNTR;
  raw10[2]=DCMIPP->P0PPCR; raw10[3]=DCMIPP->P0DCLMTR;
  raw10[4]=CSI->VC0CFGR1; raw10[5]=DCMIPP->P0FSCR;
  raw10[6]=DCMIPP->CMSR2; raw10[7]=0;
  volatile uint32_t *guard=(volatile uint32_t *)(RAW_FRAME_ADDRESS+BYTES);
  for(unsigned i=0;i<8;++i) if(guard[i]!=(0xA15A1000U+i)) raw10[7]|=1U<<i;
  CPROF[CP_DMA_BYTES]=raw10[1]; CPROF[CP_CANARY_MASK]=raw10[7]^255U;
  if(raw10[1]!=BYTES || raw10[7]) MAGIC_FAIL(0x81,-1);
  CPROF[CP_FLAGS]=CP_F_GEOMETRY|CP_F_CANARY;
  CYCLE_MARK(FRAME_GEOMETRY_DONE);

  uint16_t line_length=0;
  MAGIC_CHECK(0x54,rd16(&sensor,0x0300,&line_length)); TRACE[47]=line_length;
  early_sensor[11]=line_length;
  if(line_length!=1236U) MAGIC_FAIL(0x7D,-1);
  uint8_t raw_bits=0,raw_dt=0;
  MAGIC_CHECK(0x82,rd8(&sensor,0x030A,&raw_bits));
  MAGIC_CHECK(0x83,rd8(&sensor,0x030F,&raw_dt));
  raw10[8]=raw_bits; raw10[9]=raw_dt;
  CPROF[CP_BITS]=raw_bits; CPROF[CP_DATA_TYPE]=raw_dt;
  if(raw_bits!=10U || raw_dt!=0x30U) MAGIC_FAIL(0x84,-1);
  uint16_t exposure_coarse=0;
  MAGIC_CHECK(0x8A,rd16(&sensor,0x0064,&exposure_coarse));
  /* Nominal sensor VT pixel clock from the frozen 160.8 MHz configuration;
   * retain the fractional line duration until the final integer-us rounding. */
  capture_exposure_us=((uint64_t)exposure_coarse*line_length*10000U+804000U)/1608000U;
  TRACE[46]=exposure_coarse;
  early_sensor[20]=exposure_coarse;early_sensor[21]=capture_exposure_us;
  if(exposure_coarse!=RAW_EXPOSURE_COARSE) MAGIC_FAIL(0x90,-1);
#if RAW_EXPOSURE_COARSE != 1428
  uint16_t frame_length=0,margin=0;
  MAGIC_CHECK(0x91,rd16(&sensor,0x0458,&frame_length));
  MAGIC_CHECK(0x92,rd16(&sensor,0x0946,&margin));
  early_sensor[18]=frame_length;early_sensor[19]=margin;
  if(frame_length<margin+7U || exposure_coarse>frame_length-margin-7U)
    MAGIC_FAIL(0x93,-1);
#endif
  CPROF[CP_FLAGS]|=CP_F_RAW10;
  CPROF[CP_ESSENTIAL_DONE]=DWT->CYCCNT;
  CYCLE_MARK(FRAME_SENSOR_READS_DONE);
#if CAPTURE_DIAGNOSTICS
  CPROF[CP_DIAGNOSTIC_READS_BEGIN]=DWT->CYCCNT;
  uint16_t coarse=0,sensor_rom=0;
  MAGIC_CHECK(0x53,rd16(&sensor,0x0064,&coarse)); TRACE[46]=coarse;
  MAGIC_CHECK(0x7E,rd16(&sensor,0x0014,&sensor_rom)); early_sensor[10]=sensor_rom;
  uint8_t sensor_orientation=0;
  MAGIC_CHECK(0x7F,rd8(&sensor,0x001A,&sensor_orientation)); early_sensor[17]=sensor_orientation;
  uint32_t clock_value;
  for(unsigned i=0;i<4;++i) { MAGIC_CHECK(0x60+i,rd32(&sensor,0x0034+i*4,&clock_value)); TRACE[52+i]=clock_value; }
  MAGIC_CHECK(0x64,rd32(&sensor,0x0044,&clock_value)); TRACE[56]=clock_value;
  uint8_t clock_byte;
  MAGIC_CHECK(0x65,rd8(&sensor,0x0048,&clock_byte)); TRACE[57]=clock_byte;
  MAGIC_CHECK(0x66,rd16(&sensor,0x0458,&coarse)); TRACE[58]=coarse;
  CPROF[CP_DIAGNOSTIC_READS_DONE]=DWT->CYCCNT;
  CPROF[CP_FLAGS]|=CP_F_REGISTER_DUMPS;
#endif

  /* Preserve idle-checked data disable before sensor STOP. */
  CYCLE_MARK(PIPE_STOP_BEGIN);
  fast_snapshot(435); CPROF[CP_PIPE_STOP_BEGIN]=DWT->CYCCNT;
  MAGIC_CHECK(32, HAL_DCMIPP_CSI_PIPE_Stop(&hcam,DCMIPP_PIPE0,DCMIPP_VIRTUAL_CHANNEL0));
  CPROF[CP_PIPE_STOP_DONE]=DWT->CYCCNT; fast_snapshot(439);
  CYCLE_MARK(PIPE_STOP_DONE);
#if FAST_SHUTDOWN_DATA_OFF
  MAGIC_CHECK(0xA5,fast_shutdown_data_off());
#else
#error "Profile proof requires the qualified idle-checked data disable"
#endif
  CPROF[CP_DATA_OFF_DONE]=DWT->CYCCNT;
  CYCLE_MARK(DATA_LANES_OFF);
#if RAW_ASYNC_STOP
  CYCLE_MARK(SENSOR_STOP_COMMAND_BEGIN);
  MAGIC_CHECK(33,wr8(&sensor,0x0202,1U));
  CYCLE_MARK(SENSOR_STOP_COMMAND_DONE);
  capture_stop_started=DWT->CYCCNT; capture_stop_pending=1U;
#else
  MAGIC_CHECK(33, VD6G_Stop(&sensor));
  CPROF[CP_SENSOR_STOP_DONE]=DWT->CYCCNT;
  CPROF[CP_FLAGS]|=CP_F_SAFE_STOP;
  capture_sensor_stopped=1U;
#endif
  fast_snapshot(436); __DSB();
#if CAPTURE_DIAGNOSTICS
  CPROF[CP_SCAN_BEGIN]=DWT->CYCCNT;
  uint32_t min=255,max=0,sum=0,hash=2166136261U;
  for (unsigned i=0;i<BYTES;++i) { uint32_t v=g_frame[i]; if(v<min)min=v; if(v>max)max=v; sum+=v; hash=(hash^v)*16777619U; }
  TRACE[8]=min; TRACE[9]=max; TRACE[10]=sum; TRACE[11]=hash;
  CPROF[CP_FNV]=hash; CPROF[CP_SCAN_DONE]=DWT->CYCCNT;
  CPROF[CP_FLAGS]|=CP_F_FULL_SCAN;
#else
  TRACE[8]=0U; TRACE[9]=0U; TRACE[10]=0U; TRACE[11]=0U;
#endif
  TRACE[5]=frames; TRACE[6]=vsyncs; TRACE[7]=errors;
  TRACE[12]=(uint32_t)g_frame; TRACE[13]=BYTES; TRACE[14]=WIDTH; TRACE[15]=HEIGHT;
  TRACE[4] |= hcam.ErrorCode;
  CPROF[CP_ERRORS]=TRACE[4]|errors;
  if(frames!=1U || CPROF[CP_ERRORS]) MAGIC_FAIL(0x85,-1);
  CPROF[CP_FLAGS]|=CP_F_ERRORS;
  fast_snapshot(440); if(FAST[3]) MAGIC_FAIL(0xA2,-1); FAST[1]=40;
  CPROF[CP_HANDOFF_READY]=DWT->CYCCNT;
  __DMB(); CPROF[CP_STATE]=2U; __DMB();
#if RAW_LINE_STREAM
  if(raw_producer_complete(&raw_producer,raw10[1],frames,
      errors|hcam.ErrorCode,raw10[7],DWT->CYCCNT)) { capture_async_error=0x8FU;return; }
#endif
  capture_ready=1U; __DSB();
  CYCLE_MARK(FRAME_VALIDATED);
  raw_capture_data_ready();
  if(capture_sensor_stopped) raw_capture_stopped();
  event(40);
}
