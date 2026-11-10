"""Execute the actual finite idle-card WFI probe with a native register model."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
PREFIX = r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#define RAW_FLASH 0
#define RAW_STANDBY 0
#define RAW_DMA_SLEEP 1
#define RAW_MAGIC_FORMAT 1
#define RAW_OP_CAPTURE 1U
#define SD_ERR_WAIT 77
#define DWT_CTRL_CYCCNTENA_Msk 1U
#define RCC_MEMLPENR_AXISRAM1LPEN 1U
#define RCC_MEMLPENR_AXISRAM2LPEN 2U
#define RCC_MEMLPENR_AXISRAM3LPEN 4U
#define RCC_MEMLPENR_AXISRAM4LPEN 8U
#define RCC_MEMLPENR_AXISRAM5LPEN 16U
#define RCC_MEMLPENR_AXISRAM6LPEN 32U
#define RCC_AHB3LPENR_RIFSCLPEN 1U
#define RCC_AHB3LPENR_RISAFLPEN 2U
#define RCC_BUSLPENR_ACLKNLPEN 1U
#define RCC_BUSLPENR_ACLKNCLPEN 2U
#define RCC_AHB5ENR_SDMMC2EN 1U
#define RCC_AHB5RSTR_SDMMC2RST 1U
#define RCC_AHB5LPENR_SDMMC2LPEN 1U
#define RCC_APB4ENR2_BSECEN 1U
#define RCC_APB4LPENR2_BSECLPEN 1U
#define RCC_MISCENR_DBGEN 1U
#define RCC_MISCRSTR_DBGRST 1U
#define SDMMC_STA_CPSMACT 1U
#define SDMMC_STA_DPSMACT 2U
#define SysTick_CTRL_ENABLE_Msk 1U
#define SysTick_CTRL_TICKINT_Msk 2U
#define SysTick_CTRL_CLKSOURCE_Msk 4U
#define SCB_SCR_SLEEPONEXIT_Msk 2U
#define SCB_SCR_SLEEPDEEP_Msk 4U
#define DBGMCU_CR_DBG_SLEEP 1U
static struct { uint32_t MEMLPENR,AHB3LPENR,BUSLPENR,AHB5ENR,AHB5RSTR,
 AHB5LPENR,APB4ENR2,APB4LPENR2,MISCENR,MISCRSTR; } rcc;
static struct { uint32_t SCR,CFSR,HFSR; } scb;
static struct { uint32_t CTRL,LOAD; } systick;
static struct { uint32_t CTRL,CYCCNT; } dwt;
static struct { uint32_t CR; } dbg;
static struct { uint32_t STA,IDMACTRL; } sd;
#define RCC (&rcc)
#define SCB (&scb)
#define SysTick (&systick)
#define DWT (&dwt)
#define DBGMCU (&dbg)
#define SDMMC2_S (&sd)
typedef struct { uint32_t initialized,controller_owned,timer_owned,media_idle,
 error,cleanup_error,command_count; uint64_t written_sectors; } sd_card_t;
typedef struct { uint32_t (*milliseconds)(void); } sd_dma_wait_t;
typedef struct { uint32_t mode; } sd_stream_t;
#define SD_STREAM_NONE 0U
static sd_stream_t raw_stream;
static sd_card_t raw_card;
static sd_dma_wait_t raw_dma_wait;
static uint32_t raw_dma_sleep_clocks[18];
static uint32_t operation=1,storage_call_depth=1,SystemCoreClock=400000000;
static uint32_t valid=1,stopped=1,capture_fault,ipsr,primask,basepri,faultmask;
static uint32_t ticks,nops,wfis,mode;
static uint32_t get_tick(void) { return ticks; }
static uint32_t raw_capture_frame_validated(void) { return valid; }
static uint32_t raw_capture_sensor_stopped(void) { return stopped; }
static uint32_t raw_capture_fault(void) { return capture_fault; }
static uint32_t __get_IPSR(void) { return ipsr; }
static uint32_t __get_PRIMASK(void) { return primask; }
static uint32_t __get_BASEPRI(void) { return basepri; }
static uint32_t __get_FAULTMASK(void) { return faultmask; }
static void __DSB(void) {}
static void __NOP(void) {
 nops++;
 if(mode!=2)dwt.CYCCNT+=100000U;
 if(mode!=1&&mode!=2&&!(nops%4))ticks++;
 if(mode==9)ticks+=6;
}
static void __WFI(void) {
 wfis++;dwt.CYCCNT+=1000;
 if(mode!=3)ticks++;
 if(mode==4)primask=1;
 if(mode==5)raw_card.command_count++;
 if(mode==6)raw_card.written_sectors++;
 if(mode==7)scb.CFSR=1;
 if(mode==8)ticks+=40;
}
'''
SUFFIX = r'''
#define CHECK(x) do { if(!(x)){fprintf(stderr,"line%d: %s\n",__LINE__,#x);return 1;} } while(0)
int main(int argc,char **argv) {
 if(argc!=2)return 2;
 unsigned test=(unsigned)strtoul(argv[1],0,0),expected=0,life=0,context=0;
 rcc.MEMLPENR=63;rcc.AHB3LPENR=3;rcc.BUSLPENR=3;
 rcc.AHB5ENR=rcc.AHB5LPENR=rcc.APB4ENR2=rcc.APB4LPENR2=rcc.MISCENR=1;
 dwt.CTRL=1;dwt.CYCCNT=1234;systick.CTRL=7;systick.LOAD=399999;
 raw_card.initialized=raw_card.controller_owned=raw_card.timer_owned=raw_card.media_idle=1;
 raw_card.command_count=15;raw_dma_sleep_clocks[6]=1;raw_dma_wait.milliseconds=get_tick;
 sd_card_t *card=&raw_card;sd_dma_wait_t *wait=&raw_dma_wait;
 switch(test) {
 case 0:break;
 case 1:ticks=0xFFFFFFF0U;break;
 case 2:dwt.CYCCNT=0xFFF00000U;break;
 case 3:primask=1;context=SD_WAIT_PRIMASK;break;
 case 4:rcc.APB4ENR2=0;context=SD_WAIT_BSEC_CLOCK;break;
 case 5:rcc.APB4LPENR2=0;context=SD_WAIT_BSEC_CLOCK;break;
 case 6:dbg.CR=1;context=SD_WAIT_DEBUG_SLEEP;break;
 case 7:scb.SCR=4;context=SD_WAIT_DEEP_SLEEP;break;
 case 8:basepri=1;context=SD_WAIT_BASEPRI;break;
 case 9:ipsr=1;context=SD_WAIT_EXCEPTION;break;
 case 10:raw_dma_wait.milliseconds=0;life=1;break;
 case 11:valid=0;life=2;break;
 case 12:stopped=0;life=2;break;
 case 13:raw_card.controller_owned=0;life=4;break;
 case 14:raw_card.timer_owned=0;life=4;break;
 case 15:raw_card.media_idle=0;life=4;break;
 case 16:raw_card.error=1;life=4;break;
 case 17:raw_card.cleanup_error=1;life=4;break;
 case 18:rcc.AHB5ENR=0;life=8;break;
 case 19:rcc.AHB5RSTR=1;life=8;break;
 case 20:sd.STA=SDMMC_STA_CPSMACT;life=16;break;
 case 21:sd.STA=SDMMC_STA_DPSMACT;life=16;break;
 case 22:sd.IDMACTRL=1;life=16;break;
 case 23:raw_card.written_sectors=0x100000000ULL;life=32;break;
 case 24:raw_dma_sleep_clocks[6]=0;life=64;break;
 case 25:raw_dma_sleep_clocks[7]=1;life=64;break;
 case 26:SystemCoreClock=50000000;life=128;break;
 case 27:dwt.CTRL=0;life=128;break;
 case 28:scb.HFSR=1;life=128;break;
 case 29:systick.LOAD=0;context=SD_WAIT_SYSTICK_LOAD;break;
 case 30:systick.CTRL=5;context=SD_WAIT_SYSTICK_CTRL;break;
 case 31:rcc.MEMLPENR=0;context=SD_WAIT_RAM_CLOCKS;break;
 case 32:rcc.AHB3LPENR=0;context=SD_WAIT_RIF_CLOCKS;break;
 case 33:rcc.BUSLPENR=0;context=SD_WAIT_BUS_CLOCKS;break;
 case 34:rcc.AHB5LPENR=0;context=SD_WAIT_SD_CLOCK;break;
 case 35:rcc.MISCENR=0;context=SD_WAIT_DEBUG_ACCESS;break;
 case 36:rcc.MISCRSTR=1;context=SD_WAIT_DEBUG_ACCESS;break;
 case 37:faultmask=1;context=SD_WAIT_FAULTMASK;break;
 case 38:scb.SCR=2;context=SD_WAIT_SLEEP_ON_EXIT;break;
 case 39:card=0;life=1;break;
 case 40:wait=0;life=1;break;
 case 41:storage_call_depth=0;life=1;break;
 case 42:operation=2;life=1;break;
 case 43:capture_fault=1;life=2;break;
 case 44:mode=1;expected=2;break;
 case 45:mode=2;expected=2;break;
 case 46:mode=3;expected=3;break;
 case 47:mode=4;expected=4;context=SD_WAIT_PRIMASK;break;
 case 48:mode=5;expected=4;life=32;break;
 case 49:mode=6;expected=4;life=32;break;
 case 50:mode=7;expected=4;life=128;break;
 case 51:mode=8;expected=3;break;
 case 52:mode=9;expected=2;break;
 case 53:raw_card.initialized=0;life=4;break;
 default:return 3;
 }
 if(!expected&&(life||context))expected=1;
 CHECK(raw_dma_sleep_probe_run(card,wait)==SD_ERR_WAIT);
 volatile uint32_t *v=raw_dma_sleep_probe;
 CHECK(v[0]==0x31505344U&&v[1]==1U&&v[3]==expected);
 CHECK(v[2]==(expected?15U:4U));
 CHECK(v[4]==context&&v[5]==life);
 CHECK(v[14]==v[15]&&v[14]==wfis&&wfis<=1000);
 CHECK(v[20]==scb.CFSR&&v[21]==scb.HFSR);
 if(!expected) {
  CHECK(nops==12&&wfis==20);
  CHECK((uint32_t)(v[7]-v[6])==3&&(uint32_t)(v[9]-v[8])==1200000U);
  CHECK((uint32_t)(v[11]-v[10])==20&&(uint32_t)(v[13]-v[12])==20000U);
  CHECK(v[16]==15&&v[17]==15&&!v[18]&&!v[19]);
  CHECK(!v[22]&&!v[23]);
 }
 if(expected==1)CHECK(!nops&&!wfis);
 if(expected==2)CHECK(!wfis);
 if(test==46)CHECK(wfis==1000);
 if(test==18||test==19)CHECK(v[22]==0xFFFFFFFFU&&v[23]==0xFFFFFFFFU);
 /* The function leaves the caller's tick configuration and IRQ masks alone. */
 CHECK(systick.LOAD==(test==29?0U:399999U));
 CHECK(systick.CTRL==(test==30?5U:7U));
 return 0;
}
'''


class DmaSleepProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('clang') or shutil.which('gcc')
        if not compiler:
            raise RuntimeError('host C compiler required')
        header = (HERE.parent / 'sd-storage' / 'sd_card.h').read_text()
        enum = re.search(r'enum \{\s*SD_WAIT_NO_CLOCK=.*?\n\};', header, re.S)
        if not enum:
            raise RuntimeError('SD wait fault enum missing')
        cls.temp = tempfile.TemporaryDirectory()
        source = Path(cls.temp.name) / 'probe.c'
        cls.binary = source.with_suffix('.exe')
        source.write_text(PREFIX + enum.group(0) + '\n' +
                          (HERE / 'dma_sleep_probe.inc').read_text() + SUFFIX)
        result = subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra',
                                 '-Werror', str(source), '-o', str(cls.binary)],
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_success_wrap_stall_and_all_live_admission_failures(self):
        for case in range(54):
            with self.subTest(case=case):
                result = subprocess.run([str(self.binary), str(case)], capture_output=True,
                                        text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_probe_never_writes_card_or_reconfigures_timer_irq(self):
        source = (HERE / 'dma_sleep_probe.inc').read_text()
        self.assertNotRegex(source, r'\bsd_(?:init|read|write|sync|reset|erase|deinit)\w*\(')
        self.assertNotRegex(source, r'(?:SysTick|NVIC|SCB|RCC|SDMMC2_S|DBGMCU)->\w+\s*[|&]?=')
        self.assertNotIn('__disable_irq', source)
        self.assertNotIn('__enable_irq', source)


if __name__ == '__main__':
    unittest.main()
