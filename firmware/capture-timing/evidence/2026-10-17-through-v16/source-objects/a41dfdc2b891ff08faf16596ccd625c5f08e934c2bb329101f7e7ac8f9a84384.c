/* Bench-only reset-to-capture timing harness, October 2026.
 * Uses the pinned ST HAL and VD6G driver; no persistent writes or UART.
 * Native RAW8 dump preserves the first complete frame, without ISP settling.
 */
#include "stm32n6xx_hal.h"
#include "stm32n6xx_nucleo.h"
#include "stm32n6xx_nucleo_bus.h"
#include "vd6g.h"
#include <stdint.h>
#include <stdarg.h>

#define WIDTH 1120U
#define HEIGHT 1364U
#define BYTES (WIDTH * HEIGHT)
#define TRACE ((volatile uint32_t *)0x341F0000U)
#define EVENTS ((volatile uint32_t *)0x341F0100U)
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
__attribute__((section(".psram_bss"),aligned(32))) uint8_t g_frame[BYTES];
DCMIPP_HandleTypeDef hcam;
static VD6G_Ctx_t sensor;
static volatile uint32_t frames, vsyncs, errors;
static volatile uint32_t irq_sr0, irq_sr1;
extern void baseline_clocks(void);
extern HAL_StatusTypeDef MX_DCMIPP_ClockConfig(DCMIPP_HandleTypeDef *);

/* Called before SystemInit/BSS. No stack-backed state survives this function.
 * This volatile debug opening is the same documented sequence as the verified
 * awake marker. It does not touch OTP or lifecycle configuration. */
void capture_early(void)
{
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
  /* Reserved retained-RAM request, tested by the host before autonomous NOR
   * experiments. Normal path has no wait. ROM may erase RAM; until qualified,
   * this is only an extra recovery option, not a guaranteed recovery mechanism. */
  volatile uint32_t *gate = (volatile uint32_t *)0x341F0F00U;
  if(gate[0]==0x434D4149U && gate[1]==~0x434D4149U) {
    gate[0]=0; gate[1]=0; TRACE[0]=0x43545031; TRACE[1]=0x4D41494E;
    __DSB();
    for (;;) __NOP();
  }
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

__attribute__((noreturn)) static void fail(uint32_t where, int32_t result)
{
  TRACE[3] = (uint32_t)result;
  TRACE[4] = hcam.ErrorCode;
  event(0x80000000U | where);
  for (;;) __NOP();
}
static void check(uint32_t where, int result) { if (result) fail(where, result); }
void SysTick_Handler(void) { HAL_IncTick(); }
void DCMIPP_IRQHandler(void) { HAL_DCMIPP_IRQHandler(&hcam); }
void CSI_IRQHandler(void) { irq_sr0=CSI->SR0; irq_sr1=CSI->SR1; HAL_DCMIPP_CSI_IRQHandler(&hcam); }
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
  __HAL_RCC_CSI_FORCE_RESET(); __HAL_RCC_CSI_RELEASE_RESET();
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
    volatile uint32_t *r=(volatile uint32_t *)0x341F1000U+n*8;
    r[0]=id; r[1]=DWT->CYCCNT; r[2]=HAL_GetTick(); r[3]=h->ErrorCode;
    r[4]=irq_sr0; r[5]=irq_sr1; r[6]=h->Instance->CMSR2; r[7]=TRACE[1];
    TRACE[36]=n+1;
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
{ (void)ctx; return BSP_I2C2_ReadReg16(0x20, a, v, 1); }
static int rd16(VD6G_Ctx_t *ctx, uint16_t a, uint16_t *v)
{ (void)ctx; return BSP_I2C2_ReadReg16(0x20, a, (uint8_t*)v, 2); }
static int rd32(VD6G_Ctx_t *ctx, uint16_t a, uint32_t *v)
{ (void)ctx; return BSP_I2C2_ReadReg16(0x20, a, (uint8_t*)v, 4); }
static int wr8(VD6G_Ctx_t *ctx, uint16_t a, uint8_t v)
{
  (void)ctx;
  if (a == 0x0201 && v == 1) event(24);
  int r = BSP_I2C2_WriteReg16(0x20, a, &v, 1);
  if (a == 0x0201 && v == 1) event(25);
  return r;
}
static int wr16(VD6G_Ctx_t *ctx, uint16_t a, uint16_t v)
{ (void)ctx; return BSP_I2C2_WriteReg16(0x20, a, (uint8_t*)&v, 2); }
static int wr32(VD6G_Ctx_t *ctx, uint16_t a, uint32_t v)
{ (void)ctx; return BSP_I2C2_WriteReg16(0x20, a, (uint8_t*)&v, 4); }
static int wrarray(VD6G_Ctx_t *ctx, uint16_t a, uint8_t *data, int len)
{
  (void)ctx;
  while (len) {
    int n = len > 128 ? 128 : len;
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

int main(void)
{
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
  VD6G_Config_t config = { .ext_clock_freq_in_hz=12000000, .resolution=VD6G_RES_FULL_1120_1364,
    .frame_rate=30, .flip_mirror_mode=VD6G_MIRROR_FLIP_NONE, .exposure_mode=VD6G_EXPOSURE_MANUAL,
    .out_itf={2,1,1,1,0} };
  for (unsigned i=0; i<VD6G_GPIO_NB; ++i) config.gpio_ctrl[i]=VD6G_GPIO_GPIO_IN;
  event(6);
  check(12, VD6G_Init(&sensor, &config));
  event(12);
  /* GPIO0 exposure strobe is active only while STREAMING. The CCA-only
   * GPIO_UPDATE applies GPIO1 high first so the fitted translator is A->B.
   * PA0 has been input throughout. No standby toggle is called a route proof. */
  if(BENCH_STROBE) {
    check(0x40,wr8(&sensor,0x0468,0x15));
    check(0x41,wr8(&sensor,0x0201,6));
    uint8_t ack=0xFF; uint32_t started=HAL_GetTick();
    do { check(0x42,rd8(&sensor,0x0201,&ack)); if(HAL_GetTick()-started>500)fail(0x42,-100); } while(ack);
    check(0x43,wr8(&sensor,0x0471,0)); check(0x44,wr8(&sensor,0x0472,0));
    check(0x45,wr8(&sensor,0x0467,0x02));
    check(0x46,wr8(&sensor,0x0201,6));
    started=HAL_GetTick();
    do { check(0x47,rd8(&sensor,0x0201,&ack)); if(HAL_GetTick()-started>500)fail(0x47,-100); } while(ack);
    gpio.Pin=GPIO_PIN_0; gpio.Mode=GPIO_MODE_IT_RISING_FALLING; gpio.Pull=GPIO_NOPULL;
    HAL_GPIO_Init(GPIOA,&gpio);
    __HAL_GPIO_EXTI_CLEAR_RISING_IT(GPIO_PIN_0); __HAL_GPIO_EXTI_CLEAR_FALLING_IT(GPIO_PIN_0);
    TRACE[35]=HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_0);
    HAL_NVIC_SetPriority(EXTI0_IRQn,3,0); HAL_NVIC_EnableIRQ(EXTI0_IRQn);
    TRACE[30]=2; /* Configured, not yet independently validated. */
  }
  check(13, VD6G_SetExposureTime(&sensor, 10000));
  check(14, VD6G_SetAnalogGain(&sensor, 0));
  check(15, VD6G_SetDigitalGain(&sensor, 256));
  event(15);
  hcam.Instance=DCMIPP;
  check(16, MX_DCMIPP_ClockConfig(&hcam));
  check(17, HAL_DCMIPP_Init(&hcam));
  DCMIPP_CSI_ConfTypeDef csi={ .NumberOfLanes=DCMIPP_CSI_TWO_DATA_LANES,
    .DataLaneMapping=DCMIPP_CSI_PHYSICAL_DATA_LANES, .PHYBitrate=DCMIPP_CSI_PHY_BT_800 };
  check(18, HAL_DCMIPP_CSI_SetConfig(&hcam,&csi));
  check(19, HAL_DCMIPP_CSI_SetVCConfig(&hcam,DCMIPP_VIRTUAL_CHANNEL0,DCMIPP_CSI_DT_BPP8));
  DCMIPP_CSI_PIPE_ConfTypeDef pcsi={ .DataTypeMode=DCMIPP_DTMODE_DTIDA, .DataTypeIDA=DCMIPP_DT_RAW8 };
  check(20, HAL_DCMIPP_CSI_PIPE_SetConfig(&hcam,DCMIPP_PIPE0,&pcsi));
  DCMIPP_PipeConfTypeDef pipe={ .FrameRate=DCMIPP_FRAME_RATE_ALL };
  check(21, HAL_DCMIPP_PIPE_SetConfig(&hcam,DCMIPP_PIPE0,&pipe));
  /* Avoid full-buffer CPU initialization before first exposure. No D-cache is
   * enabled; fixed RAM region is written only by the snapshot DMA. */
  event(21);
  check(22, HAL_DCMIPP_CSI_PIPE_Start(&hcam,DCMIPP_PIPE0,DCMIPP_VIRTUAL_CHANNEL0,(uint32_t)g_frame,DCMIPP_MODE_SNAPSHOT));
  event(22);
  check(26, VD6G_Start(&sensor));
  event(26);
  uint32_t start=HAL_GetTick();
  while (!frames) if (HAL_GetTick()-start > 2000) fail(28,-100);
  event(31);
  /* Snapshot stops DMA after the complete first frame; sensor stream can be
   * stopped now, without changing the already frozen capture. */
  check(32, HAL_DCMIPP_CSI_PIPE_Stop(&hcam,DCMIPP_PIPE0,DCMIPP_VIRTUAL_CHANNEL0));
  check(33, VD6G_Stop(&sensor));
  __DSB();
  uint32_t min=255,max=0,sum=0,hash=2166136261U;
  for (unsigned i=0;i<BYTES;++i) { uint32_t v=g_frame[i]; if(v<min)min=v; if(v>max)max=v; sum+=v; hash=(hash^v)*16777619U; }
  TRACE[5]=frames; TRACE[6]=vsyncs; TRACE[7]=errors; TRACE[8]=min; TRACE[9]=max; TRACE[10]=sum; TRACE[11]=hash;
  TRACE[12]=(uint32_t)g_frame; TRACE[13]=BYTES; TRACE[14]=WIDTH; TRACE[15]=HEIGHT;
  TRACE[4] |= hcam.ErrorCode;
  event(40);
  for (;;) __NOP();
}
