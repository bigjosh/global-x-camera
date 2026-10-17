"""Offline reproducible capture benchmark build; never accesses hardware."""
import argparse, hashlib, json, re, subprocess, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
VENDOR=REPO/'tmp/bringup/x-cube-n6-camera-capture'
TC=Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.12.3.rel1.win32_1.0.200.202406191623/tools/bin')
sys.path.insert(0,str(REPO/'firmware/boot-timing'))
from add_boot_header import make_image,inspect_image

def sha(b): return hashlib.sha256(b).hexdigest()
def function(text,signature):
    begin=text.index(signature+'\n{')
    start=text.index('{',begin); depth=1; end=start+1
    while depth:
        depth += (text[end]=='{')-(text[end]=='}'); end+=1
    return text[begin:end]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--snapshot',type=Path)
    p.add_argument('--capture-source',type=Path,default=HERE/'capture.c',help='Optional frozen harness source for matched single-variable experiments')
    p.add_argument('--i2c-hz',type=int,default=100000,choices=[100000,400000,1000000])
    p.add_argument('--reset-us',type=int,default=10000)
    p.add_argument('--poll-us',type=int,default=10000)
    p.add_argument('--strobe',type=int,choices=[0,1],default=1)
    p.add_argument('--stop-stage',type=int,choices=[0,1,2,3],default=0)
    p.add_argument('--minimal-system-init',action='store_true')
    p.add_argument('--rom-clocks',action='store_true')
    p.add_argument('--i2c-timing',type=lambda s:int(s,0))
    p.add_argument('--newest-only',action='store_true')
    p.add_argument('--lto',action='store_true')
    p.add_argument('--fix-dphy-irq',action='store_true')
    p.add_argument('--prepare-early',action='store_true')
    p.add_argument('--gpio-level',type=int,choices=[-1,0,1],default=-1)
    p.add_argument('--coarse-lines',type=int,default=0)
    p.add_argument('--direct-clocks',action='store_true')
    p.add_argument('--batch-config',action='store_true')
    p.add_argument('--stage2',action='store_true',help='Link at 0x34190000; stage1 releases reset and owns DWT/trace')
    p.add_argument('--phy-testclk-us',type=int,default=0,help='Experimental DWT delay replacing HAL 1ms PHY test-clock delay; 0 preserves HAL')
    p.add_argument('--frame-lines',type=int,default=0,help='Direct frame-length override after vendor setup; 0 preserves vendor value')
    p.add_argument('--receiver-before-ready',action='store_true',help='Stage2 only: configure/arm receiver while stage1-released sensor is starting')
    p.add_argument('--pll-prediv1',action='store_true',help='Documented-boundary sensor trial: 12MHz /1 *67 instead of /2 *134, same 804MHz')
    p.add_argument('--clock-diagnostics',action='store_true',help='Read applied sensor clocks after first complete frame')
    p.add_argument('--phy-target-low-e2',action='store_true',help='Correct pinned HAL low oscillator-target byte address from E3 to E2')
    p.add_argument('--phy-ccfr',type=int,default=None,help='Override both PHY config-clock range writes; nominal20MHz gives12')
    p.add_argument('--skip-sensor-reset',action='store_true',help='Monolithic cold-boot trial: preload PO5 high and omit software sensor reset')
    p.add_argument('--receiver-only',action='store_true',help='Stage2 for early-START prefix: preserve sensor setup and arm within4.5ms')
    p.add_argument('--prestart-dwell-us',type=int,default=0,help='Diagnostic dwell after sensor setup, immediately before START write')
    p.add_argument('--i2c-follower',action='store_true',help='Diagnostic I2C_SYNC mode with one trigger after entering STREAMING')
    p.add_argument('--sensor-late-diagnostics',action='store_true',help='Receiver-only: read ROM/orientation/line diagnostics after first frame')
    a=p.parse_args(); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    assert 0<=a.phy_testclk_us<=1000
    assert a.frame_lines==0 or 1503<=a.frame_lines<=65535
    assert not a.receiver_before_ready or a.stage2 or a.skip_sensor_reset
    assert a.phy_ccfr is None or 0<=a.phy_ccfr<=63
    assert not a.skip_sensor_reset or (not a.stage2 and a.rom_clocks)
    assert not a.receiver_only or (a.stage2 and a.coarse_lines==1428 and a.frame_lines==4336 and a.strobe==1 and not a.pll_prediv1)
    assert 0<=a.prestart_dwell_us<=100000
    assert not a.i2c_follower or not a.receiver_only
    assert not a.sensor_late_diagnostics or a.receiver_only
    harness=a.capture_source.read_text()
    original_harness=harness
    # These tightly scoped transformations let a new experiment reuse a frozen
    # known-good harness instead of unintentionally incorporating source drift.
    if a.receiver_before_ready and 'BENCH_RECEIVER_EARLY' not in harness:
        start=harness.index('  hcam.Instance=DCMIPP;')
        end=harness.index('  event(22);',start)+len('  event(22);')
        block=harness[start:end]
        harness=harness[:start]+'  prepare_receiver();'+harness[end:]
        harness=harness.replace('  prepare_receiver();','',1)
        harness=harness.replace('int main(void)\n{','static void prepare_receiver(void)\n{\n'+block+'\n}\n\nint main(void)\n{',1)
        harness=harness.replace('  event(6);','  prepare_receiver(); /* BENCH_RECEIVER_EARLY: sensor reset was released by stage1. */\n  event(6);',1)
    if a.frame_lines and 'BENCH_FRAME_LINES' not in harness:
        harness=harness.replace('  event(12);','  event(12);\n  check(0x55,wr16(&sensor,0x0458,BENCH_FRAME_LINES));',1)
    if a.clock_diagnostics and 'BENCH_CLOCK_DIAGNOSTICS' not in harness:
        marker='  check(0x54,rd16(&sensor,0x0300,&line_length)); TRACE[47]=line_length;'
        assert marker in harness
        harness=harness.replace(marker,marker+'''
  /* BENCH_CLOCK_DIAGNOSTICS: after first frame, before stream stop. */
  uint32_t clock_value;
  for(unsigned i=0;i<4;++i) { check(0x60+i,rd32(&sensor,0x0034+i*4,&clock_value)); TRACE[52+i]=clock_value; }
  check(0x64,rd32(&sensor,0x0044,&clock_value)); TRACE[56]=clock_value;
  uint8_t clock_byte;
  check(0x65,rd8(&sensor,0x0048,&clock_byte)); TRACE[57]=clock_byte;
  check(0x66,rd16(&sensor,0x0458,&coarse)); TRACE[58]=coarse;
''',1)
    if a.skip_sensor_reset:
        old='  HAL_PWREx_EnableVddIO2();'
        assert harness.count(old)==1
        harness=harness.replace(old,'''  /* Cold-only no-reset trial. Preserve the module's natural startup.
   * Preload HIGH before output mode so the frozen GPIO initialization cannot
   * assert XSHUTDOWN. Unexpected active drive/pulls stop awake for inspection. */
  __HAL_RCC_GPIOO_CLK_ENABLE();
  TRACE[48]=GPIOO->MODER; TRACE[49]=GPIOO->ODR; TRACE[50]=GPIOO->IDR;
  TRACE[51]=PWR->SVMCR3; TRACE[59]=GPIOO->PUPDR; TRACE[60]=GPIOO->OTYPER;
  uint32_t po5_mode=(GPIOO->MODER>>10)&3U;
  if((po5_mode!=0 && po5_mode!=3) || (GPIOO->PUPDR & (3U<<10))) fail(0x70,-1);
  event(148);
  GPIOO->BSRR=GPIO_PIN_5;
  __DSB();
  HAL_PWREx_EnableVddIO2();
  event(149);''',1)
    if a.receiver_only:
        begin=harness.index('  VD6G_Config_t config =')
        end=harness.index('  uint32_t start=HAL_GetTick();',begin)
        replacement='''  /* Receiver-only handoff. Stage1 has already completed START's I2C write.
   * This deadline is intentionally earlier than the measured first STROBE;
   * a miss aborts the experiment and never claims a first-frame capture. */
  volatile uint32_t *early_sensor=(volatile uint32_t *)0x341F4000U;
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
    (void)HAL_DCMIPP_CSI_PIPE_Stop(&hcam,DCMIPP_PIPE0,DCMIPP_VIRTUAL_CHANNEL0);
    (void)wr8(&sensor,0x0202,1); /* Request stop; recorded failure remains authoritative. */
    fail(0x74,-1);
  }
  event(250);
  uint8_t state=0xFF; uint32_t ack_started=HAL_GetTick();
  do { check(0x75,rd8(&sensor,0x0201,&state)); if(HAL_GetTick()-ack_started>500U) fail(0x75,-100); } while(state);
  do { check(0x76,rd8(&sensor,0x0028,&state)); if(HAL_GetTick()-ack_started>500U) fail(0x76,-100); } while(state!=3U);
  sensor.ctx.is_streaming=1;
  TRACE[28]=TRACE[35]; TRACE[29]=HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_0);
  event(26);
'''
        harness=harness[:begin]+replacement+harness[end:]
    if a.i2c_follower:
        marker='  event(12);'
        assert harness.count(marker)==1
        harness=harness.replace(marker,marker+'''
  uint8_t vt_ctrl=0;
  check(0x78,rd8(&sensor,0x0309,&vt_ctrl));
  check(0x79,wr8(&sensor,0x0309,(vt_ctrl & ~3U) | 2U));
  check(0x7A,wr16(&sensor,0x033A,0));
''',1)
        marker='  event(26);'
        assert harness.count(marker)==1
        harness=harness.replace(marker,marker+'''
  TRACE[61]=DWT->CYCCNT; event(152);
  check(0x7B,wr8(&sensor,0x0202,2));
  TRACE[62]=DWT->CYCCNT; event(153);
''',1)
        marker='  event(31);'
        assert harness.count(marker)==1
        harness=harness.replace(marker,marker+'''
  uint8_t sync_ack=0xFF; uint32_t sync_wait=HAL_GetTick();
  do { check(0x7C,rd8(&sensor,0x0202,&sync_ack)); if(HAL_GetTick()-sync_wait>500U) fail(0x7C,-100); } while(sync_ack);
''',1)
    if a.sensor_late_diagnostics:
        marker='  check(0x54,rd16(&sensor,0x0300,&line_length)); TRACE[47]=line_length;'
        assert marker in harness
        harness=harness.replace(marker,marker+'''
  /* Read-only checks deferred until the first frame is safely in RAM. */
  early_sensor[11]=line_length;
  if(line_length!=1236U) fail(0x7D,-1);
  uint16_t sensor_rom=0;
  check(0x7E,rd16(&sensor,0x0014,&sensor_rom)); early_sensor[10]=sensor_rom;
  uint8_t sensor_orientation=0;
  check(0x7F,rd8(&sensor,0x001A,&sensor_orientation)); early_sensor[17]=sensor_orientation;
''',1)
    if a.batch_config: assert a.coarse_lines>0 and a.gpio_level==-1,'Batch fixed profile requires explicit coarse exposure and STROBE mode'
    pin=subprocess.check_output(['git','-C',str(VENDOR),'rev-parse','HEAD'],text=True).strip()
    assert pin=='e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a'
    fw=VENDOR/'STM32Cube_FW_N6/Drivers'
    maintext=(VENDOR/'Src/main.c').read_text()
    clocks='#include "stm32n6xx_hal.h"\n#include "stm32n6xx_nucleo.h"\n'
    clocks+=function(maintext,'static void SystemClock_Config(void)').replace('static void SystemClock_Config','void baseline_clocks')+'\n'
    clocks+=function(maintext,'HAL_StatusTypeDef MX_DCMIPP_ClockConfig(DCMIPP_HandleTypeDef *hdcmipp)')+'\n'
    if a.rom_clocks:
        # Measured ROM PLL1 is 1200MHz; IC1 /3 gives CPU400MHz.
        # IC17 /4 gives DCMIPP300MHz; IC18 /60 gives CSI20MHz.
        clocks=clocks.replace('RCC_PeriphCLKInitStruct.ICSelection[RCC_IC17].ClockSelection = RCC_ICCLKSOURCE_PLL2;', 'RCC_PeriphCLKInitStruct.ICSelection[RCC_IC17].ClockSelection = RCC_ICCLKSOURCE_PLL1;')
        clocks=clocks.replace('RCC_PeriphCLKInitStruct.ICSelection[RCC_IC17].ClockDivider = 3;', 'RCC_PeriphCLKInitStruct.ICSelection[RCC_IC17].ClockDivider = 4;')
        clocks=clocks.replace('RCC_PeriphCLKInitStruct.ICSelection[RCC_IC18].ClockDivider = 40;', 'RCC_PeriphCLKInitStruct.ICSelection[RCC_IC18].ClockDivider = 60;')
    if a.direct_clocks:
        assert a.rom_clocks,'Direct clock variant requires measured ROM clock configuration'
        clocks='''/* Same operations as pinned HAL CSI/DCMIPP clock branches. */
#include "stm32n6xx_hal.h"
void baseline_clocks(void) {}
HAL_StatusTypeDef MX_DCMIPP_ClockConfig(DCMIPP_HandleTypeDef *hdcmipp)
{
  (void)hdcmipp;
  MODIFY_REG(RCC->IC18CFGR,RCC_IC18CFGR_IC18SEL|RCC_IC18CFGR_IC18INT,
             RCC_ICCLKSOURCE_PLL1|(59U<<RCC_IC18CFGR_IC18INT_Pos));
  LL_RCC_IC18_Enable();
  MODIFY_REG(RCC->IC17CFGR,RCC_IC17CFGR_IC17SEL|RCC_IC17CFGR_IC17INT,
             RCC_ICCLKSOURCE_PLL1|(3U<<RCC_IC17CFGR_IC17INT_Pos));
  LL_RCC_IC17_Enable();
  __HAL_RCC_DCMIPP_CONFIG(RCC_DCMIPPCLKSOURCE_IC17);
  return HAL_OK;
}
'''
    (out/'clocks.c').write_text(clocks,encoding='utf-8',newline='\n')
    startup=(fw/'CMSIS/Device/ST/STM32N6xx/Source/Templates/gcc/startup_stm32n657xx.s').read_text()
    startup=startup.replace('/* Call the clock system initialization function.*/','  bl capture_early\n/* Call the clock system initialization function.*/')
    startup=startup.replace('  bl __libc_init_array','  nop /* No C++/constructor objects are linked in this bare-metal image. */')
    (out/'startup.s').write_text(startup,encoding='utf-8',newline='\n')
    link=(VENDOR/'Gcc/STM32N657xx_nucleo.ld').read_text()
    # Reserve maintenance helpers and trace buffer above the <64KiB payload.
    link=link.replace('LENGTH =  447K','LENGTH =  111K')
    if a.stage2:
        link=link.replace('ORIGIN = 0x34180400','ORIGIN = 0x34190000')
    (out/'capture.ld').write_text(link,encoding='utf-8',newline='\n')
    systemtext=(fw/'CMSIS/Device/ST/STM32N6xx/Source/Templates/system_stm32n6xx_fsbl.c').read_text()
    if a.minimal_system_init:
        systemtext=systemtext.replace(function(systemtext,'void SystemInit(void)'),'''void SystemInit(void)
{
  SCB->VTOR = INTVECT_START;
  SCB->CPACR |= (3UL<<20U) | (3UL<<22U);
  __DSB(); __ISB();
}''')
    (out/'system.c').write_text(systemtext,encoding='utf-8',newline='\n')
    includes=[VENDOR/'Inc',fw/'CMSIS/Include',fw/'CMSIS/Device/ST/STM32N6xx/Include',fw/'STM32N6xx_HAL_Driver/Inc',fw/'STM32N6xx_HAL_Driver/Inc/Legacy',fw/'BSP/STM32N6xx_Nucleo',fw/'BSP/Components/Common',VENDOR/'Lib/Camera_Middleware/sensors/vd6g']
    names=['stm32n6xx_hal','stm32n6xx_hal_cortex','stm32n6xx_hal_dcmipp','stm32n6xx_hal_gpio','stm32n6xx_hal_i2c','stm32n6xx_hal_i2c_ex','stm32n6xx_hal_pwr','stm32n6xx_hal_pwr_ex','stm32n6xx_hal_rcc','stm32n6xx_hal_rcc_ex','stm32n6xx_hal_rif']
    driver=(VENDOR/'Lib/Camera_Middleware/sensors/vd6g/vd6g.c').read_text()
    driver=driver.replace('#include "vd6g.h"','#include "vd6g.h"\nextern void bench_delay_us(uint32_t us);\nextern void bench_sensor_event(uint32_t id);\nextern uint32_t bench_cycles(void);\nextern uint32_t bench_cycles_per_ms(void);')
    driver=driver.replace('  ctx->delay(ctx, 10);','  bench_delay_us(BENCH_RESET_US);')
    if a.stage2 or a.skip_sensor_reset:
        reset='  ctx->shutdown_pin(ctx, 0);\n  bench_delay_us(BENCH_RESET_US);\n  ctx->shutdown_pin(ctx, 1);\n  bench_delay_us(BENCH_RESET_US);'
        assert driver.count(reset)==1
        note='Stage1 asserted/released XSHUTDOWN' if a.stage2 else 'Cold-only no-reset trial preserves natural sensor startup'
        driver=driver.replace(reset,f'  /* {note}; continue READY polling without reset. */')
    driver=driver.replace(function(driver,'static int VD6G_PollReg8(VD6G_Ctx_t *ctx, uint16_t addr, uint8_t poll_val)'),'''static int VD6G_PollReg8(VD6G_Ctx_t *ctx, uint16_t addr, uint8_t poll_val)
{
  uint32_t start=bench_cycles(), timeout=bench_cycles_per_ms()*500U;
  uint32_t tries=0; uint8_t val; int ret;
  do {
    ret=ctx->read8(ctx,addr,&val);
    if(!ret && val==poll_val) return 0;
    /* Only hardware-reset READY polling tolerates a not-yet-awake NACK. */
    if(ret && !(addr==VD6G_REG_SYSTEM_FSM && poll_val==VD6G_SYSTEM_FSM_READY_TO_BOOT)) return ret;
    bench_delay_us(BENCH_POLL_US);
  } while((uint32_t)(bench_cycles()-start)<timeout && ++tries<1000000U);
  return -1;
}''')
    for n,call in enumerate(['VD6G_WaitState(ctx, VD6G_SYSTEM_FSM_READY_TO_BOOT)','VD6G_CheckModelId(ctx)','VD6G_ApplyPatch(ctx)','VD6G_BootMcu(ctx)','VD6G_ApplyVtPatch(ctx)','VD6G_SetBayerType(ctx)','VD6G_Gpios(ctx)','VD6G_SetupEarly(ctx)','VD6G_Setup(ctx)','VD6G_StartStreaming(ctx)'],100):
        driver=driver.replace(f'  ret = {call};',f'  bench_sensor_event({n});\n  ret = {call};')
    if a.newest_only:
        driver=driver.replace('ret = VD6G_ApplyPatchSlowBoot(ctx);','ret = -1; /* This experiment accepts fast-boot silicon only. */')
        driver=driver.replace('ret = VD6G_ApplyVtPatchSlowBoot(ctx);','ret = -1; /* No old-silicon VT patch payload in this image. */')
    if a.batch_config:
        driver=driver.replace(function(driver,'static int VD6G_Gpios(VD6G_Ctx_t *ctx)'),'''static int VD6G_Gpios(VD6G_Ctx_t *ctx)
{
  return ctx->write_array(ctx,VD6G_REG_GPIO_x_CTRL(0),ctx->ctx.config_save.gpio_ctrl,VD6G_GPIO_NB);
}''')
    if a.pll_prediv1:
        old='  ret = ctx->write32(ctx, VD6G_REG_EXT_CLOCK, drv_ctx->config_save.ext_clock_freq_in_hz);'
        assert driver.count(old)==1
        driver=driver.replace(old,'''  /* UM2602 lists inclusive 12MHz PLL input and 1/67 register defaults.
   * Pinned driver chooses strictly below 12MHz; this is a separate experiment. */
  if(drv_ctx->config_save.ext_clock_freq_in_hz!=12000000U) return -1;
  pll_prediv=1; pll_mult=67;
'''+old)
    if a.prestart_dwell_us:
        old='  ret = ctx->write8(ctx, VD6G_REG_STBY, VD6G_CMD_START_STREAM);'
        assert driver.count(old)==1
        driver=driver.replace(old,f'  bench_sensor_event(150); bench_delay_us({a.prestart_dwell_us}U); bench_sensor_event(151);\n'+old)
    driver+='''
/* Bench split preserves vendor setup, separating configuration from START. */
int VD6G_BenchPrepare(VD6G_Ctx_t *ctx) { return VD6G_Setup(ctx); }
int VD6G_BenchStartPrepared(VD6G_Ctx_t *ctx) {
  int r=VD6G_StartStreaming(ctx); if(!r)ctx->ctx.is_streaming=1; return r;
}
'''
    (out/'vd6g.c').write_text(driver,encoding='utf-8',newline='\n')
    bus=(fw/'BSP/STM32N6xx_Nucleo/stm32n6xx_nucleo_bus.c').read_text()
    if a.i2c_timing is not None:
        bus=bus.replace('I2C_GetTiming(HAL_RCC_GetPCLK1Freq(), BUS_I2C2_FREQUENCY)',f'0x{a.i2c_timing:08X}U /* Offline timing; manifest records clock assumption. */')
    (out/'bus.c').write_text(bus,encoding='utf-8',newline='\n')
    halcam=(fw/'STM32N6xx_HAL_Driver/Src/stm32n6xx_hal_dcmipp.c').read_text()
    if a.fix_dphy_irq:
        for lane in [0,1]:
            for flag in ['ESOT','ESOTSYNC','EESC','ESYNCESC','ECTRL']:
                original=f'__HAL_DCMIPP_CSI_DISABLE_IT(csi_instance, DCMIPP_CSI_IT_{flag}DL{lane});'
                assert halcam.count(original)==1,original
                halcam=halcam.replace(original,original.replace('_CSI_DISABLE_IT','_CSI_DPHY_DISABLE_IT'))
    if a.phy_testclk_us:
        old='  /* Set the testclk (clock enable) on during 15ns */\n  SET_BIT(csi_instance->PTCR0, CSI_PTCR0_TCKEN);\n\n  HAL_Delay(1);'
        assert halcam.count(old)==1
        new=old.replace('  HAL_Delay(1);',f'  bench_delay_us({a.phy_testclk_us}U); /* Empirical timing experiment; see manifest. */')
        halcam=halcam.replace(old,new)
        halcam='extern void bench_delay_us(unsigned int us);\n'+halcam
    if a.phy_target_low_e2:
        old='DCMIPP_CSI_WritePHYReg(csi_instance, 0x00, 0xe3, SNPS_Freqs[pCSI_Config->PHYBitrate].osc_freq_target & 0xFFU);'
        assert halcam.count(old)==1
        halcam=halcam.replace(old,old.replace('0x00, 0xe3','0x00, 0xe2'))
    if a.phy_ccfr is not None:
        old='(0x28U << CSI_PFCR_CCFR_Pos)'
        assert halcam.count(old)==2
        halcam=halcam.replace(old,f'({a.phy_ccfr}U << CSI_PFCR_CCFR_Pos)')
        old='MODIFY_REG(csi_instance->PFCR, CSI_PFCR_HSFR,'
        assert halcam.count(old)==1
        halcam=halcam.replace(old,'MODIFY_REG(csi_instance->PFCR, CSI_PFCR_HSFR | CSI_PFCR_CCFR,')
    (out/'hal_dcmipp.c').write_text(halcam,encoding='utf-8',newline='\n')
    if harness==original_harness: (out/'capture.c').write_bytes(a.capture_source.read_bytes())
    else: (out/'capture.c').write_text(harness,encoding='utf-8',newline='\n')
    sources=[out/'capture.c',out/'clocks.c',out/'startup.s',out/'system.c',fw/'BSP/STM32N6xx_Nucleo/stm32n6xx_nucleo.c',out/'bus.c',out/'vd6g.c']+[fw/f'STM32N6xx_HAL_Driver/Src/{n}.c' for n in names]
    sources=[out/'hal_dcmipp.c' if x.name=='stm32n6xx_hal_dcmipp.c' else x for x in sources]
    gcc=str(TC/'arm-none-eabi-gcc.exe')
    flags=['-mcpu=cortex-m55','-mthumb','-mcmse','-mfpu=fpv5-d16','-mfloat-abi=hard','-Os','-g3','-ffunction-sections','-fdata-sections','-DNDEBUG','-DSTM32N657xx','-DSTM32N6570_NUCLEO_REV','-Wall','-Wextra',f'-DBUS_I2C2_FREQUENCY={a.i2c_hz}U',f'-DBENCH_RESET_US={a.reset_us}U',f'-DBENCH_POLL_US={a.poll_us}U',f'-DBENCH_STROBE={a.strobe}']+[f'-I{x}' for x in includes]
    flags.append(f'-DBENCH_STOP_STAGE={a.stop_stage}')
    flags.append(f'-DBENCH_ROM_CLOCKS={int(a.rom_clocks)}')
    flags.extend([f'-DBENCH_PREPARE_EARLY={int(a.prepare_early)}',f'-DBENCH_GPIO_LEVEL={a.gpio_level}',f'-DBENCH_COARSE_LINES={a.coarse_lines}'])
    flags.append(f'-DBENCH_BATCH_CONFIG={int(a.batch_config)}')
    flags.append(f'-DBENCH_STAGE2={int(a.stage2)}')
    flags.append(f'-DBENCH_FRAME_LINES={a.frame_lines}')
    flags.append(f'-DBENCH_RECEIVER_EARLY={int(a.receiver_before_ready)}')
    flags.append(f'-DBENCH_CLOCK_DIAGNOSTICS={int(a.clock_diagnostics)}')
    if a.lto: flags.append('-flto')
    objs=[]
    for i,s in enumerate(sources):
        o=out/f'{i:02d}_{s.stem}.o'; objs.append(o)
        subprocess.run([gcc,*flags,'-c',str(s),'-o',str(o)],check=True)
    elf=out/'capture.elf'
    subprocess.run([gcc,*flags,'-nostartfiles','--specs=nano.specs','--specs=nosys.specs','-T',str(out/'capture.ld'),*[str(x) for x in objs],'-Wl,--gc-sections,--build-id=none,--no-warn-rwx-segments',f'-Wl,-Map={out/"capture.map"}','-lc','-lm','-lnosys','-o',str(elf)],check=True)
    subprocess.run([str(TC/'arm-none-eabi-objcopy.exe'),'-O','binary',str(elf),str(out/'capture.bin')],check=True)
    symbols=subprocess.check_output([str(TC/'arm-none-eabi-nm.exe'),'--numeric-sort',str(elf)],text=True)
    assert not re.search(r'\b(HAL_BSEC_OTP_Program|Fuse_Programming|BSP_XSPI_NOR_(?:Write|Erase)\w*)$',symbols,re.M)
    (out/'symbols.txt').write_text(symbols,encoding='utf-8')
    (out/'capture.lst').write_bytes(subprocess.check_output([str(TC/'arm-none-eabi-objdump.exe'),'-d',str(elf)]))
    size=subprocess.check_output([str(TC/'arm-none-eabi-size.exe'),str(elf)],text=True)
    payload=(out/'capture.bin').read_bytes()
    if a.stage2:
        import struct
        stack,entry=struct.unpack_from('<II',payload)
        assert 0x34190000<=(entry&~1)<0x34190000+len(payload) and entry&1
        image=b''
        image_metadata={'vector_address':'0x34190000','stack_pointer':f'0x{stack:08x}','entry_point':f'0x{entry:08x}'}
    else:
        image=make_image(payload); (out/'capture_boot.bin').write_bytes(image)
        image_metadata=inspect_image(image)
    manifest={**image_metadata,'vendor_commit':pin,'raw_bytes':len(payload),'raw_sha256':sha(payload),'boot_bytes':len(image),'boot_sha256':sha(image) if image else None,'size':size,'trace_address':'0x341f0000','event_address':'0x341f0100','frame_address':'0x34000000','frame_bytes':1527680,'hardware_status':'untested','parameters':{'i2c_hz':a.i2c_hz,'reset_us':a.reset_us,'poll_us':a.poll_us,'strobe':a.strobe},'sources':{str(s.relative_to(REPO)):sha(s.read_bytes()) for s in sources}}
    manifest['parameters'].update(stop_stage=a.stop_stage,minimal_system_init=a.minimal_system_init,rom_clocks=a.rom_clocks,i2c_timing=a.i2c_timing,newest_only=a.newest_only,lto=a.lto,fix_dphy_irq=a.fix_dphy_irq)
    manifest['parameters'].update(prepare_early=a.prepare_early,gpio_level=a.gpio_level,coarse_lines=a.coarse_lines)
    manifest['parameters']['direct_clocks']=a.direct_clocks
    manifest['parameters']['batch_config']=a.batch_config
    manifest['parameters']['stage2']=a.stage2
    manifest['parameters'].update(phy_testclk_us=a.phy_testclk_us,frame_lines=a.frame_lines)
    manifest['parameters']['receiver_before_ready']=a.receiver_before_ready
    manifest['capture_source_path']=str(a.capture_source.resolve())
    manifest['parameters'].update(pll_prediv1=a.pll_prediv1,clock_diagnostics=a.clock_diagnostics)
    manifest['parameters'].update(phy_target_low_e2=a.phy_target_low_e2,phy_ccfr=a.phy_ccfr)
    manifest['parameters']['skip_sensor_reset']=a.skip_sensor_reset
    manifest['parameters']['receiver_only']=a.receiver_only
    manifest['parameters']['sensor_late_diagnostics']=a.sensor_late_diagnostics
    manifest['parameters']['prestart_dwell_us']=a.prestart_dwell_us
    manifest['parameters']['i2c_follower']=a.i2c_follower
    if a.snapshot:
        assert not a.stage2,'Stage2 requires the combined stage1 image builder'
        saved=a.snapshot.read_bytes(); assert len(saved)==65536 and len(image)<=65536
        sector=image+saved[len(image):]; (out/'capture_sector_0.bin').write_bytes(sector)
        manifest.update(program_sha256=sha(sector),snapshot_sha256=sha(saved))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest,indent=2))
if __name__=='__main__': main()
