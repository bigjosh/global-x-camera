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

/* v30 diagnostic region: header32, 128 bounded raw snapshots of12 words. */
#define LATE ((volatile uint32_t *)0x343F8000U)
#define LATE_WORDS (32U+128U*12U)
#define STOP_DATA (CSI_SR1_STOPDL0F | CSI_SR1_STOPDL1F)
__attribute__((noreturn)) static void fail(uint32_t where,int32_t result);

static void late_snapshot(uint32_t id)
{
  uint32_t mask=__get_PRIMASK(); __disable_irq();
  uint32_t n=LATE[2];
  if(n<128U) {
    volatile uint32_t *r=LATE+32U+n*12U;
    r[0]=id; r[1]=DWT->CYCCNT; r[2]=HAL_GetTick();
    r[11]=RCC->APB5RSTR;
    if(!(r[11]&RCC_APB5RSTR_CSIRST) &&
       (RCC->APB5ENR&RCC_APB5ENR_CSIEN) && (RCC->DIVENR&RCC_DIVENR_IC18EN)) {
      r[3]=CSI->SR0; r[4]=CSI->SR1; r[5]=CSI->IER0; r[6]=CSI->IER1;
      r[7]=CSI->PRCR; r[8]=CSI->PCR; r[9]=CSI->CR; r[10]=CSI->LMCFGR;
      LATE[4]|=r[3]; LATE[5]|=r[4];
    } else {
      /* Reading an APB peripheral while its RCC reset is held can stall the
       * bus. Do not fabricate a measured reset state: PRCR=FFFFFFFF means
       * all CSI fields in this record were deliberately not read. */
      for(unsigned i=3;i<=10;++i) r[i]=0;
      r[7]=0xFFFFFFFFU; LATE[7]++;
    }
    LATE[2]=n+1U;
  } else LATE[3]++;
  LATE[1]=id; __DMB(); __set_PRIMASK(mask);
}

static void late_init(void)
{
  for(unsigned i=0;i<LATE_WORDS;++i) LATE[i]=0;
  LATE[0]=0x4C505231U; LATE[6]=LATE_PHY_MODE;
  volatile uint32_t *s=(volatile uint32_t *)0x343F4000U;
  for(unsigned i=0;i<8;++i) LATE[8+i]=s[24+i];
  late_snapshot(299);
}

/* Called around merger writes and the actual physical PHY reset release. */
void late_phy_hook(unsigned int id)
{
  event(id); late_snapshot(id);
  if(id==303U && ((CSI->PRCR & CSI_PRCR_PEN) ||
                 (CSI->CR & CSI_CR_CSIEN) || (CSI->SR1 & CSI_SR1_ACTCLF))) fail(0x93,-1);
}

/* All failure paths stay debug-accessible. No flash operation is performed by
 * this image. The owner must inspect this terminal state before maintenance. */
__attribute__((noreturn,noinline,used)) void late_failure_park(void)
{
  __disable_irq(); __DSB(); __ISB();
  __asm volatile(".global late_failure_idle\n"
                 "late_failure_idle:\n"
                 "b.n .\n");
  __builtin_unreachable();
}

__attribute__((noreturn)) static void late_failure_quiesce(uint32_t where,int32_t result)
{
  __disable_irq();
  LATE[16]=where; LATE[17]=(uint32_t)result;
  late_snapshot(0xF0000000U | where);
  LATE[25]=RCC->APB5ENR;
  if((LATE[25]&RCC_APB5ENR_DCMIPPEN) &&
     !(RCC->APB5RSTR&RCC_APB5RSTR_DCMIPPRST) && (RCC->DIVENR&RCC_DIVENR_IC17EN)) {
    LATE[26]=DCMIPP->P0FCTCR; LATE[27]=DCMIPP->CMSR2;
  }
  LATE[28]=RCC->APB5RSTR;
  /* Only DCMIPP: stop capture/DMA without clearing the CSI error history. */
  RCC->APB5RSTSR=RCC_APB5RSTSR_DCMIPPRSTS; __DSB();
  LATE[29]=RCC->APB5RSTR; LATE[18]=__get_PRIMASK();
  LATE[19]=((LATE[29]&RCC_APB5RSTR_DCMIPPRST) && LATE[18]==1U)?0x51554945U:0U;
  __DSB(); __ISB(); late_failure_park();
}

static void qualify_stop(void)
{
  uint32_t begun=HAL_GetTick(),stable=0,previous=~CSI->SR1;
  for(unsigned attempts=0;attempts<10000000U;++attempts) {
    uint32_t sr=CSI->SR1;
    if(sr!=previous) { late_snapshot(308); previous=sr; }
    if((sr&STOP_DATA)==STOP_DATA) {
      if(!stable) stable=DWT->CYCCNT;
      /* Observe the two data STOP flags continuously for100 nominalus.
       * This is a conservative observation guard, not a claimed PHY T_INIT. */
      if((uint32_t)(DWT->CYCCNT-stable)>=40000U) {
        LATE[20]=sr; LATE[21]=DWT->CYCCNT;
        event(309); late_snapshot(309); return;
      }
    } else stable=0;
    if(LATE[3]) fail(0x94,-2);
    if(HAL_GetTick()-begun>50U) break;
  }
  late_snapshot(0xF0000094U); fail(0x94,-100);
}

/* Diagnostic sensor frame2, with the original DCMIPP snapshot still armed.
 * Never resets the PHY/receiver, clears errors, or silently discards a frame. */
static void qualify_second_trigger(uint32_t scan)
{
  uint32_t began=HAL_GetTick(),start_cycles=DWT->CYCCNT,stable=0;
  unsigned rises=0,falls=0;
  event(329); late_snapshot(329);
  for(unsigned attempts=0;attempts<10000000U;++attempts) {
    uint32_t count=TRACE[2];
    if(count>=200U || LATE[3]) fail(0x94,-2);
    while(scan<count) {
      uint32_t id=EVENTS[scan*4U]; ++scan;
      if(id==50U) ++rises;
      if(id==51U) {
        if(rises!=1U || falls) fail(0x96,-3);
        falls=1; event(330); late_snapshot(330);
      }
    }
    if(frames || vsyncs || rises>1U) fail(0x96,-4);
    uint32_t sr=CSI->SR1;
    if(falls && (sr&(STOP_DATA|CSI_SR1_STOPCLF))==(STOP_DATA|CSI_SR1_STOPCLF)) {
      if(!stable) stable=DWT->CYCCNT;
      if((uint32_t)(DWT->CYCCNT-stable)>=40000U) {
        event(331); late_snapshot(331); return;
      }
    } else stable=0;
    if(HAL_GetTick()-began>500U || (uint32_t)(DWT->CYCCNT-start_cycles)>200000000U) break;
  }
  fail(0x98,falls ? -204 : -203);
}

__attribute__((noreturn)) static void fail(uint32_t where, int32_t result)
{
  __disable_irq(); /* Keep terminal TRACE proof immutable before quiescence. */
  TRACE[3] = (uint32_t)result;
  TRACE[4] = hcam.ErrorCode;
  event(0x80000000U | where);
  late_failure_quiesce(where,result);
}
static void check(uint32_t where, int result) { if (result) fail(where, result); }
void SysTick_Handler(void) { HAL_IncTick(); }
void DCMIPP_IRQHandler(void) { HAL_DCMIPP_IRQHandler(&hcam); }
void CSI_IRQHandler(void) { late_snapshot(320); irq_sr0=CSI->SR0; irq_sr1=CSI->SR1; irq_ier0=CSI->IER0; irq_ier1=CSI->IER1; HAL_DCMIPP_CSI_IRQHandler(&hcam); }
void EXTI0_IRQHandler(void) { HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_0); }
void HAL_GPIO_EXTI_Rising_Callback(uint16_t pin) { if(pin==GPIO_PIN_0) event(50); }
void HAL_GPIO_EXTI_Falling_Callback(uint16_t pin) { if(pin==GPIO_PIN_0) event(51); }
void HardFault_Handler(void) {
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
  late_snapshot(301);
  if(!(RCC->APB5RSTR & RCC_APB5RSTR_CSIRST)) fail(0x91,-1);
  __HAL_RCC_CSI_RELEASE_RESET(); __DSB();
  late_snapshot(302);
  if((RCC->APB5RSTR & RCC_APB5RSTR_CSIRST) || (CSI->PRCR & CSI_PRCR_PEN)) fail(0x92,-1);
  HAL_NVIC_SetPriority(DCMIPP_IRQn, 7, 0); HAL_NVIC_EnableIRQ(DCMIPP_IRQn);
  HAL_NVIC_SetPriority(CSI_IRQn, 7, 0); HAL_NVIC_EnableIRQ(CSI_IRQn);
}
void HAL_DCMIPP_PIPE_FrameEventCallback(DCMIPP_HandleTypeDef *h, uint32_t pipe)
{ (void)h; if (pipe == 0) { frames++; event(30); } }
void HAL_DCMIPP_PIPE_VsyncEventCallback(DCMIPP_HandleTypeDef *h, uint32_t pipe)
{ (void)h; if (pipe == 0) { vsyncs++; event(29); } }
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
  event(22);
}

int main(void)
{
  late_init();
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
  /* Matched follower control: both configurations keep all sensor settings
   * equal; only receiver initialization relative to START ACK differs. */
  volatile uint32_t *early_sensor=(volatile uint32_t *)0x343F4000U;
  if(early_sensor[0]!=0x53454E31U || early_sensor[1]!=37U || early_sensor[2]) fail(0x71,-1);
  if(early_sensor[28]!=2U || early_sensor[29] || early_sensor[30]!=0x0CU ||
     !(early_sensor[31]&RCC_APB5RSTR_CSIRST)) fail(0x95,-1);
  uint32_t sensor_start_end=early_sensor[5];
  TRACE[62]=(uint32_t)(DWT->CYCCNT-sensor_start_end); TRACE[63]=0;
  gpio.Pin=GPIO_PIN_0; gpio.Mode=GPIO_MODE_IT_RISING_FALLING; gpio.Pull=GPIO_NOPULL;
  HAL_GPIO_Init(GPIOA,&gpio);
  __HAL_GPIO_EXTI_CLEAR_RISING_IT(GPIO_PIN_0); __HAL_GPIO_EXTI_CLEAR_FALLING_IT(GPIO_PIN_0);
  TRACE[35]=HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_0);
  if(TRACE[35]) fail(0x73,-1);
  HAL_NVIC_SetPriority(EXTI0_IRQn,3,0); HAL_NVIC_EnableIRQ(EXTI0_IRQn);
  TRACE[30]=2;
  if(!LATE_PHY_MODE) prepare_receiver();
  uint8_t state=0xFF; uint32_t ack_started=HAL_GetTick();
  do { check(0x75,rd8(&sensor,0x0201,&state)); if(HAL_GetTick()-ack_started>500U) fail(0x75,-100); } while(state);
  do { check(0x76,rd8(&sensor,0x0028,&state)); if(HAL_GetTick()-ack_started>500U) fail(0x76,-100); } while(state!=3U);
  sensor.ctx.is_streaming=1; LATE[22]=DWT->CYCCNT;
  event(26); late_snapshot(307);
  if(LATE_PHY_MODE) prepare_receiver();
  qualify_stop();
  if(frames || vsyncs || HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_0)) fail(0x96,-1);
  arm_receiver();
  early_sensor[16]=DWT->CYCCNT;
  TRACE[61]=(uint32_t)(early_sensor[16]-sensor_start_end);
  event(250); late_snapshot(310);
  if(LATE[3]) fail(0x94,-2);
  uint8_t fsync=0xFF;
  check(0x97,rd8(&sensor,0x0202,&fsync));
  if(fsync) fail(0x97,-1);
  uint32_t first_trigger_scan=TRACE[2];
  LATE[23]=DWT->CYCCNT; event(152); late_snapshot(311);
  check(0x97,wr8(&sensor,0x0202,2));
  LATE[24]=DWT->CYCCNT; event(153); late_snapshot(312);
  TRACE[28]=TRACE[35]; TRACE[29]=HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_0);
  /* Diagnostic only: preserve the armed receiver and capture sensor frame2.
   * The first physical exposure is intentionally not counted as a captured frame. */
  qualify_second_trigger(first_trigger_scan);
  ack_started=HAL_GetTick();
  do { check(0x98,rd8(&sensor,0x0202,&state));
       if(HAL_GetTick()-ack_started>500U) fail(0x98,-201); } while(state);
  check(0x98,rd8(&sensor,0x0028,&state));
  if(state!=3U) fail(0x98,-202);
  if(frames || vsyncs || HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_0)) fail(0x96,-2);
  event(332); late_snapshot(332);
  if(LATE[3]) fail(0x94,-2);
  LATE[30]=DWT->CYCCNT; event(334); late_snapshot(334);
  check(0x98,wr8(&sensor,0x0202,2));
  LATE[31]=DWT->CYCCNT; event(335); late_snapshot(335);
  uint32_t start=HAL_GetTick();
  while (!frames) if (HAL_GetTick()-start > 2000) fail(28,-100);
  event(31); late_snapshot(313);
  /* I2C FSYNC acknowledgement follows transmission, never wait before frame. */
  ack_started=HAL_GetTick();
  do { check(0x98,rd8(&sensor,0x0202,&state));
       if(HAL_GetTick()-ack_started>500U) fail(0x98,-100); } while(state);
  late_snapshot(314);
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
  late_snapshot(315);
  check(32, HAL_DCMIPP_CSI_PIPE_Stop(&hcam,DCMIPP_PIPE0,DCMIPP_VIRTUAL_CHANNEL0));
  check(33, VD6G_Stop(&sensor));
  late_snapshot(316);
  __DSB();
  uint32_t min=255,max=0,sum=0,hash=2166136261U;
  for (unsigned i=0;i<BYTES;++i) { uint32_t v=g_frame[i]; if(v<min)min=v; if(v>max)max=v; sum+=v; hash=(hash^v)*16777619U; }
  TRACE[5]=frames; TRACE[6]=vsyncs; TRACE[7]=errors; TRACE[8]=min; TRACE[9]=max; TRACE[10]=sum; TRACE[11]=hash;
  TRACE[12]=(uint32_t)g_frame; TRACE[13]=BYTES; TRACE[14]=WIDTH; TRACE[15]=HEIGHT;
  TRACE[4] |= hcam.ErrorCode;
  late_snapshot(317); if(LATE[3]) fail(0x94,-2); LATE[1]=40;
  event(40);
  for (;;) __NOP();
}
