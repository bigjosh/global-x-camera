"""Offline checks of the knob mapping, the knob reader and the exposure gate.

The real knob_map.h and knob.c are compiled for the host against a register
model; no hardware or instrument is touched. These tests show the logic is
self-consistent. They do not show that a camera takes correct pictures.
"""
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tables = load('knob_tables')
gate = load('exposure_gate')
package = load('package')
CAPTURE = HERE / 'evidence/2026-11-13-d8-hold/capture-input'
COMPILER = shutil.which('clang') or shutil.which('gcc')


def python_map(exposure_code, gain_code):
    """Independent model of knob_map() in knob_map.h."""
    def position(code):
        if code <= tables.CODE_LOW:
            return 0
        if code >= tables.CODE_HIGH:
            return 1024
        return (code - tables.CODE_LOW) * 1024 // (tables.CODE_HIGH - tables.CODE_LOW)
    exposure, gain = tables.exposure_table(), tables.gain_table()
    where = position(exposure_code)
    index, fraction = where >> 5, where & 31
    lines = exposure[-1] if index >= tables.STEPS else \
        exposure[index] + (((exposure[index + 1] - exposure[index]) * fraction) >> 5)
    frame = min(max(lines + tables.FRAME_MARGIN, tables.DEFAULT_FRAME), tables.FRAME_MAX)
    return lines, frame, gain[min((position(gain_code) + 16) >> 5, tables.STEPS)]


class TableTests(unittest.TestCase):
    def test_committed_header_is_what_the_generator_produces(self):
        self.assertEqual((HERE / 'knob_tables.h').read_text(encoding='utf-8'), tables.render())

    def test_ranges_follow_the_sensor_limits(self):
        exposure, gain = tables.exposure_table(), tables.gain_table()
        self.assertEqual((exposure[0], exposure[-1]), (tables.MIN_LINES, tables.MAX_LINES))
        self.assertGreaterEqual(tables.MIN_LINES, 21)                 # driver minimum
        self.assertLessEqual(tables.MAX_LINES + tables.FRAME_MARGIN, tables.FRAME_MAX)
        self.assertEqual((gain[0], gain[-1]), (0, 28))                # 1x .. 8x
        self.assertTrue(all(b > a for a, b in zip(exposure, exposure[1:])))
        self.assertTrue(all(0 <= b - a <= 2 for a, b in zip(gain, gain[1:])))
        # Equal steps of travel are equal exposure ratios, within rounding.
        ratio = (tables.MAX_LINES / tables.MIN_LINES) ** (1 / tables.STEPS)
        for a, b in zip(exposure[8:], exposure[9:]):
            self.assertAlmostEqual(b / a, ratio, delta=0.01)
        self.assertEqual(tables.LINE_NS, 7686)

    def test_default_bytes_match_the_installed_prefix(self):
        prefix = (CAPTURE / 'stage1.bin').read_bytes()
        manual, frame = package.knob_sites(prefix)
        self.assertEqual((manual, frame), (0x3418179C, 0x34181328))
        self.assertEqual(tables.movw_r1(4336), bytes.fromhex('41f2f001'))
        # The same sites are present, unmoved, in the package prefix that adds the hook.
        self.assertEqual(prefix[frame - package.PREFIX_BASE:][:4], tables.movw_r1(tables.DEFAULT_FRAME))
        self.assertEqual(prefix[manual - package.PREFIX_BASE:][:12], tables.manual_block())
        # A second copy of either pattern would make the edit ambiguous.
        second_manual = prefix[:6000] + tables.manual_block() + prefix[6012:]
        second_frame = prefix[:6000] + tables.movw_r1(4336) + bytes.fromhex('02224ff48b60') + prefix[6010:]
        for changed in (second_manual, second_frame):
            self.assertEqual(len(changed), len(prefix))
            with self.assertRaises(ValueError):
                package.knob_sites(changed)

    def test_movw_encoding_against_the_assembler(self):
        assembler = shutil.which('arm-none-eabi-as')
        if not assembler or not shutil.which('arm-none-eabi-objcopy'):
            self.skipTest('Arm assembler unavailable')
        values = [0, 1, 255, 256, 2047, 2048, 4095, 4096, 4336, 32000, 65000, 65535]
        with tempfile.TemporaryDirectory(prefix='knob-movw-') as tmp:
            root = Path(tmp)
            (root / 'm.s').write_text('.syntax unified\n.thumb\n' + ''.join(f' movw r1,#{v}\n' for v in values))
            subprocess.run([assembler, '-march=armv8-m.main', str(root / 'm.s'), '-o', str(root / 'm.o')], check=True)
            subprocess.run(['arm-none-eabi-objcopy', '-O', 'binary', '-j', '.text', str(root / 'm.o'), str(root / 'm.bin')], check=True)
            code = (root / 'm.bin').read_bytes()
        self.assertEqual(code, b''.join(tables.movw_r1(v) for v in values))


@unittest.skipUnless(COMPILER, 'Native C compiler unavailable')
class MappingTests(unittest.TestCase):
    def test_every_adc_code_maps_as_the_model_says(self):
        with tempfile.TemporaryDirectory(prefix='knob-map-') as tmp:
            root = Path(tmp)
            (root / 'main.c').write_text(r'''
#include <stdio.h>
#include "knob_map.h"
int main(void){
 for(uint32_t code=0;code<4096;code++){
  struct knob_setting s=knob_map(code,code);
  printf("%u %u %u %u\n",(unsigned)code,(unsigned)s.lines,(unsigned)s.frame,(unsigned)s.gain);
 }
 for(uint32_t v=0;v<65536;v+=1)printf("m %u %08x\n",(unsigned)v,(unsigned)knob_movw_r1(v));
 return 0;
}''')
            exe = root / 'map.exe'
            subprocess.run([COMPILER, '-std=c11', '-Wall', '-Wextra', '-Werror', '-I' + str(HERE),
                            str(root / 'main.c'), '-o', str(exe)], check=True)
            lines = subprocess.check_output([str(exe)], text=True).splitlines()
        settings = [tuple(map(int, line.split())) for line in lines if not line.startswith('m')]
        self.assertEqual(len(settings), 4096)
        previous = None
        for code, exposure, frame, gain in settings:
            self.assertEqual((exposure, frame, gain), python_map(code, code), code)
            self.assertTrue(tables.MIN_LINES <= exposure <= tables.MAX_LINES)
            self.assertTrue(exposure + 68 + 7 <= frame <= tables.FRAME_MAX)   # sensor's own margin rule
            self.assertTrue(frame == tables.DEFAULT_FRAME or frame == exposure + tables.FRAME_MARGIN)
            self.assertLessEqual(gain, tables.GAIN_CODE_MAX)
            if previous:
                self.assertGreaterEqual((exposure, gain), previous)             # never reverses
            previous = (exposure, gain)
        # Both ends are reachable with margin; an open wiper reads the low end.
        self.assertEqual(settings[0][1:], (tables.MIN_LINES, tables.DEFAULT_FRAME, 0))
        self.assertEqual(settings[3839][1:], (tables.MAX_LINES, tables.MAX_LINES + tables.FRAME_MARGIN, 28))
        for line in lines:
            if line.startswith('m'):
                _, value, word = line.split()
                self.assertEqual(bytes.fromhex(word)[::-1], tables.movw_r1(int(value)))


MOCK_HAL = r'''
#include <stdint.h>
#include <string.h>
typedef struct {uint32_t AHB4ENR,AHB3ENR,AHB1ENR,AHB4ENSR,AHB3ENSR,AHB1ENSR,AHB4ENCR,AHB3ENCR,AHB1ENCR,AHB1RSTSR,AHB1RSTCR,CCIPR1;} MockRCC;
typedef struct {uint32_t MODER,PUPDR,OTYPER,OSPEEDR,ODR,BSRR,SECCFGR;} GPIO_TypeDef;
typedef struct {uint32_t SVMCR1,SVMCR3;} MockPWR;
typedef struct {uint32_t RISC_SECCFGRx[4];} MockRIFSC;
typedef struct {uint32_t ISR,CALFACT;} MockADC;
typedef struct {uint32_t CYCCNT;} MockDWT;
extern MockRCC rcc; extern GPIO_TypeDef ga,gc,gf,gg,gh; extern MockPWR pwr; extern MockRIFSC rifsc;
extern MockADC adc1; extern MockDWT dwt;
#define RCC (&rcc)
#define GPIOA (&ga)
#define GPIOC (&gc)
#define GPIOF (&gf)
#define GPIOG (&gg)
#define GPIOH (&gh)
#define PWR (&pwr)
#define RIFSC (&rifsc)
#define ADC1 (&adc1)
#define DWT (&dwt)
#define RCC_AHB4ENR_GPIOAEN 1U
#define RCC_AHB4ENR_GPIOCEN 4U
#define RCC_AHB4ENR_GPIOFEN 32U
#define RCC_AHB4ENR_GPIOGEN 64U
#define RCC_AHB4ENR_GPIOHEN 128U
#define RCC_AHB4ENR_PWREN 0x40000U
#define RCC_AHB3ENR_RIFSCEN 0x200U
#define RCC_AHB1ENR_ADC12EN 0x20U
#define RCC_AHB1RSTR_ADC12RST 0x20U
#define RCC_CCIPR1_ADC12SEL 0x70U
#define RCC_CCIPR1_ADCPRE 0xFF00U
#define PWR_SVMCR1_VDDIO4SV 0x100U
#define PWR_SVMCR1_VDDIO4VRSEL 0x1000000U
#define PWR_SVMCR3_AVMEN 0x10U
#define PWR_SVMCR3_ASV 0x1000U
#define PWR_SVMCR3_ARDY 0x100000U
typedef enum {HAL_OK=0,HAL_ERROR=1} HAL_StatusTypeDef;
typedef struct {uint32_t Resolution,ScanConvMode,EOCSelection,NbrOfConversion,ExternalTrigConv,ExternalTrigConvEdge,SamplingMode,ConversionDataManagement,Overrun;} ADC_InitTypeDef;
typedef struct {MockADC *Instance;ADC_InitTypeDef Init;uint32_t ErrorCode;} ADC_HandleTypeDef;
typedef struct {uint32_t Channel,Rank,SamplingTime,SingleDiff,OffsetNumber;} ADC_ChannelConfTypeDef;
#define ADC_RESOLUTION_12B 1U
#define ADC_SCAN_DISABLE 0U
#define ADC_EOC_SINGLE_CONV 1U
#define ADC_SOFTWARE_START 1U
#define ADC_EXTERNALTRIGCONVEDGE_NONE 0U
#define ADC_SAMPLING_MODE_NORMAL 0U
#define ADC_CONVERSIONDATA_DR 0U
#define ADC_OVR_DATA_PRESERVED 0U
#define ADC_CHANNEL_7 7U
#define ADC_CHANNEL_10 10U
#define ADC_REGULAR_RANK_1 1U
#define ADC_SAMPLETIME_1499CYCLES_5 7U
#define ADC_SINGLE_ENDED 0U
#define ADC_OFFSET_NONE 0U
HAL_StatusTypeDef HAL_ADC_Init(ADC_HandleTypeDef *);HAL_StatusTypeDef HAL_ADC_DeInit(ADC_HandleTypeDef *);
HAL_StatusTypeDef HAL_ADC_ConfigChannel(ADC_HandleTypeDef *,ADC_ChannelConfTypeDef *);
HAL_StatusTypeDef HAL_ADCEx_Calibration_Start(ADC_HandleTypeDef *,uint32_t);
HAL_StatusTypeDef HAL_ADC_Start(ADC_HandleTypeDef *);HAL_StatusTypeDef HAL_ADC_Stop(ADC_HandleTypeDef *);
HAL_StatusTypeDef HAL_ADC_PollForConversion(ADC_HandleTypeDef *,uint32_t);
uint32_t HAL_ADC_GetValue(ADC_HandleTypeDef *);uint32_t HAL_GetTick(void);
void sync_regs(void);void tick(void);
#define __DSB() sync_regs()
#define __ISB() ((void)0)
#define __NOP() tick()
'''

MOCK_MAIN = r'''
#include "knob.c"
#include <assert.h>
#include <stdio.h>
MockRCC rcc; GPIO_TypeDef ga,gc,gf,gg,gh; MockPWR pwr; MockRIFSC rifsc; MockADC adc1; MockDWT dwt;
uint8_t manual_ram[12],frame_ram[4];
static unsigned fail_step,supply_ready,active,enabled,configured,converted,ms,resets;
static uint32_t codes[2];
static void port(GPIO_TypeDef *g){g->ODR=(g->ODR|(g->BSRR&65535U))&~(g->BSRR>>16);g->BSRR=0;}
void sync_regs(void){
 rcc.AHB4ENR=(rcc.AHB4ENR|rcc.AHB4ENSR)&~rcc.AHB4ENCR;rcc.AHB4ENSR=rcc.AHB4ENCR=0;
 rcc.AHB3ENR=(rcc.AHB3ENR|rcc.AHB3ENSR)&~rcc.AHB3ENCR;rcc.AHB3ENSR=rcc.AHB3ENCR=0;
 rcc.AHB1ENR=(rcc.AHB1ENR|rcc.AHB1ENSR)&~rcc.AHB1ENCR;rcc.AHB1ENSR=rcc.AHB1ENCR=0;
 if(rcc.AHB1RSTSR&RCC_AHB1RSTR_ADC12RST)resets++;
 rcc.AHB1RSTSR=rcc.AHB1RSTCR=0;                           /* write-only set and clear registers */
 port(&ga);port(&gc);port(&gf);port(&gg);port(&gh);
 /* Ready is a status bit: it follows the monitor enable, never a write. */
 if(supply_ready&&(pwr.SVMCR3&PWR_SVMCR3_AVMEN))pwr.SVMCR3|=PWR_SVMCR3_ARDY;else pwr.SVMCR3&=~PWR_SVMCR3_ARDY;
}
void tick(void){dwt.CYCCNT+=1000U;}
uint32_t HAL_GetTick(void){sync_regs();return ms++;}
/* The knobs can only be read correctly in exactly this state. */
static void excited(void){
 sync_regs();
 assert((gf.MODER>>10&3U)==1U&&!(gf.ODR&32U));            /* PF5 drives LOW */
 assert((gf.MODER>>12&3U)==1U&&(gf.ODR&64U));             /* PF6 drives HIGH */
 assert((gc.MODER>>24&3U)==1U&&(gc.ODR&4096U));           /* PC12 drives HIGH */
 assert(!(gf.OTYPER&96U)&&!(gc.OTYPER&4096U));            /* push-pull */
 assert(!(gf.PUPDR&(15U<<10))&&!(gc.PUPDR&(3U<<24)));
 assert(pwr.SVMCR1&PWR_SVMCR1_VDDIO4SV);
 assert((ga.MODER>>16&63U)==63U&&!(ga.PUPDR>>16&63U));    /* PA8..10 analog */
 assert((gg.MODER>>30)==3U&&!(gg.PUPDR>>30));             /* PG15 analog */
 assert((gf.MODER>>6&3U)==3U&&!(gf.PUPDR>>6&3U));         /* PF3 analog */
 assert(!(gc.MODER>>20&3U)&&!(gc.PUPDR>>20&3U));          /* PC10 input */
 assert(!(gh.MODER>>4&3U)&&!(gh.PUPDR>>4&3U));            /* PH2 input */
 assert((rifsc.RISC_SECCFGRx[2]&1U)&&(pwr.SVMCR3&PWR_SVMCR3_ASV)&&(rcc.AHB1ENR&RCC_AHB1ENR_ADC12EN));
 assert((rcc.CCIPR1&(RCC_CCIPR1_ADC12SEL|RCC_CCIPR1_ADCPRE))==0x750U);
}
HAL_StatusTypeDef HAL_ADC_Init(ADC_HandleTypeDef *h){assert(h->Instance==ADC1);excited();assert(resets==1);active=1;return fail_step==4?HAL_ERROR:HAL_OK;}
HAL_StatusTypeDef HAL_ADC_DeInit(ADC_HandleTypeDef *h){(void)h;assert(!enabled);active=0;return HAL_OK;}
HAL_StatusTypeDef HAL_ADC_ConfigChannel(ADC_HandleTypeDef *h,ADC_ChannelConfTypeDef *c){
 (void)h;assert(active&&!enabled);assert(c->Channel==7U||c->Channel==10U);
 assert(c->SamplingTime==ADC_SAMPLETIME_1499CYCLES_5&&c->Rank==1U);configured=c->Channel;return HAL_OK;}
HAL_StatusTypeDef HAL_ADCEx_Calibration_Start(ADC_HandleTypeDef *h,uint32_t m){(void)h;(void)m;assert(!enabled);adc1.CALFACT=0x800000FFU;return fail_step==5?HAL_ERROR:HAL_OK;}
HAL_StatusTypeDef HAL_ADC_Start(ADC_HandleTypeDef *h){(void)h;excited();assert(dwt.CYCCNT>=400000U);enabled=1;return HAL_OK;}
HAL_StatusTypeDef HAL_ADC_Stop(ADC_HandleTypeDef *h){(void)h;enabled=0;return HAL_OK;}
HAL_StatusTypeDef HAL_ADC_PollForConversion(ADC_HandleTypeDef *h,uint32_t t){(void)h;(void)t;assert(enabled);return fail_step==6&&converted>=2?HAL_ERROR:HAL_OK;}
uint32_t HAL_ADC_GetValue(ADC_HandleTypeDef *h){(void)h;converted++;
 /* The first reading of each knob is still settling; only the second is right. */
 return (configured==10U?codes[0]:codes[1])+(converted<=2?300U:0U);}
void LL_RCC_SetADCPrescaler(uint32_t n){rcc.CCIPR1=(rcc.CCIPR1&~RCC_CCIPR1_ADCPRE)|(n<<8);}
void LL_RCC_SetADCClockSource(uint32_t s){rcc.CCIPR1=(rcc.CCIPR1&~RCC_CCIPR1_ADC12SEL)|s;}
static const uint8_t default_manual[12]={2,0,0x94,5,0,1,0,1,0,1,0,1},default_frame[4]={0x41,0xf2,0xf0,0x01};
typedef struct {MockRCC r;GPIO_TypeDef a,c,f,g,h;MockPWR p;MockRIFSC s;} State;
static State snapshot(void){sync_regs();State x={rcc,ga,gc,gf,gg,gh,pwr,rifsc};return x;}
static uint32_t run(uint32_t exposure,uint32_t gain,unsigned failure,State *before,State *after){
 memset(&rcc,0,sizeof rcc);memset(&pwr,0,sizeof pwr);memset(&rifsc,0,sizeof rifsc);memset(&adc1,0,sizeof adc1);
 /* Arbitrary inherited state that must come back exactly: pins analog as
  * after reset, other pins in assorted modes, some clocks already on. */
 ga=(GPIO_TypeDef){0xFFEAFFABU,0x24000100U,0x9000U,0x0C000000U,0x8001U,0,0xFFFFU};
 gc=(GPIO_TypeDef){0xFBFFFA55U,0x00100401U,0x0003U,0x000000F0U,0x0002U,0,0xFFFFU};
 gf=(GPIO_TypeDef){0xFFFFFFFFU,0x00000000U,0x0000U,0x00000000U,0x0000U,0,0xFFFFU};
 gg=(GPIO_TypeDef){0xFFFFFF5AU,0x00000005U,0x0001U,0x00000003U,0x0004U,0,0xFFFFU};
 gh=(GPIO_TypeDef){0xFFFFFFCFU,0x00000040U,0x0000U,0x00000000U,0x0000U,0,0xFFFFU};
 rcc.AHB4ENR=RCC_AHB4ENR_GPIOAEN|0x8U;rcc.CCIPR1=0x12340003U;pwr.SVMCR1=0x2U;pwr.SVMCR3=0x1U;rifsc.RISC_SECCFGRx[2]=0x40U;
 if(failure==1)rcc.AHB1ENR=RCC_AHB1ENR_ADC12EN;
 if(failure==2)pwr.SVMCR1|=PWR_SVMCR1_VDDIO4VRSEL;
 memcpy(manual_ram,default_manual,12);memcpy(frame_ram,default_frame,4);
 if(failure==7)frame_ram[2]^=1U;
 if(failure==9)manual_ram[5]^=1U;
 codes[0]=exposure;codes[1]=gain;fail_step=failure;supply_ready=failure!=3;
 active=enabled=configured=converted=ms=resets=0;dwt.CYCCNT=0;
 *before=snapshot();uint32_t result=knob_apply();*after=snapshot();
 assert(!active&&!enabled);
 return result;
}
int main(int argc,char **argv){
 State before,after;(void)argc;(void)argv;
 /* Success: a table of readings for the Python side to compare. */
 static const uint32_t pairs[][2]={{0,0},{120,3720},{121,3719},{2000,3000},{3840,5},{1920,1920},{700,4095},{4095,2047}};
 for(unsigned i=0;i<sizeof pairs/sizeof pairs[0];i++){
  uint32_t result=run(pairs[i][0],pairs[i][1],0,&before,&after);
  assert(result==0&&knob_proof[K_RESULT]==0&&knob_proof[K_STATE]==5&&knob_proof[K_MAGIC]==0x31424E4BU);
  assert(!memcmp(&before,&after,sizeof before));             /* every register handed back */
  assert(converted==4&&knob_proof[K_EXPOSURE_CODE]==pairs[i][0]&&knob_proof[K_GAIN_CODE]==pairs[i][1]);
  assert(knob_proof[K_EXPOSURE_FIRST]==pairs[i][0]+300U);    /* the settled pair is the one used */
  printf("%u %u",(unsigned)pairs[i][0],(unsigned)pairs[i][1]);
  for(unsigned k=0;k<12;k++)printf(" %02x",manual_ram[k]);
  for(unsigned k=0;k<4;k++)printf(" %02x",frame_ram[k]);
  printf(" %u %u %u\n",(unsigned)knob_proof[K_LINES],(unsigned)knob_proof[K_FRAME],(unsigned)knob_proof[K_GAIN]);
 }
 /* Every failure leaves the fixed exposure in place and restores the pins. */
 static const unsigned failures[]={1,2,3,4,5,6,7,9},expected[]={1,2,3,4,5,6,7,7};
 for(unsigned i=0;i<sizeof failures/sizeof failures[0];i++){
  uint8_t manual_before[12],frame_before[4];
  uint32_t result=run(2000,3000,failures[i],&before,&after);
  memcpy(manual_before,default_manual,12);memcpy(frame_before,default_frame,4);
  if(failures[i]==7)frame_before[2]^=1U;
  if(failures[i]==9)manual_before[5]^=1U;
  assert(result==expected[i]&&knob_proof[K_RESULT]==expected[i]&&knob_proof[K_STATE]!=5);
  assert(!memcmp(manual_ram,manual_before,12)&&!memcmp(frame_ram,frame_before,4));
  assert(!memcmp(&before,&after,sizeof before));
  assert(knob_proof[K_LINES]==1428U&&knob_proof[K_FRAME]==4336U&&knob_proof[K_GAIN]==0U);
  if(failures[i]<=2)assert(converted==0&&ms<=1);              /* refused before touching a pin */
 }
 puts("done");
 return 0;
}
'''


@unittest.skipUnless(COMPILER, 'Native C compiler unavailable')
class KnobReaderTests(unittest.TestCase):
    def test_reader_against_a_register_model(self):
        with tempfile.TemporaryDirectory(prefix='knob-reader-') as tmp:
            root = Path(tmp)
            for name in ('knob.c', 'knob_map.h', 'knob_tables.h'):
                shutil.copyfile(HERE / name, root / name)
            (root / 'stm32n6xx_hal.h').write_text(MOCK_HAL)
            (root / 'stm32n6xx_ll_rcc.h').write_text('#define LL_RCC_ADC_CLKSOURCE_HSI 0x50U\n'
                                                     'void LL_RCC_SetADCPrescaler(uint32_t);void LL_RCC_SetADCClockSource(uint32_t);\n')
            (root / 'knob_config.h').write_text('#include <stdint.h>\nextern uint8_t manual_ram[12],frame_ram[4];\n'
                                                '#define KNOB_MANUAL_ADDRESS ((uintptr_t)manual_ram)\n'
                                                '#define KNOB_FRAME_ADDRESS ((uintptr_t)frame_ram)\n')
            (root / 'main.c').write_text(MOCK_MAIN)
            exe = root / 'knob.exe'
            compiled = subprocess.run([COMPILER, '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-pointer-to-int-cast',
                                       '-Wno-int-conversion', '-I' + str(root), str(root / 'main.c'), '-o', str(exe)],
                                      capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            ran = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        rows = ran.stdout.split('\n')
        self.assertEqual(rows[-2], 'done')
        for row in rows[:-2]:
            fields = row.split()
            exposure_code, gain_code = int(fields[0]), int(fields[1])
            written = bytes.fromhex(''.join(fields[2:18]))
            lines, frame, gain = python_map(exposure_code, gain_code)
            self.assertEqual(written[:12], tables.manual_block(lines, gain), row)
            self.assertEqual(written[12:], tables.movw_r1(frame), row)
            self.assertEqual(tuple(map(int, fields[18:])), (lines, frame, gain))

    def test_selector_reads_knobs_only_when_the_cable_is_certainly_absent(self):
        source = (HERE / 'selector.c').read_text(encoding='utf-8')
        self.assertEqual(source.count('knob_apply()'), 1)
        self.assertIn('if(present==0){proof[9]=(uint32_t)knob_proof;proof[10]=knob_apply();}', source)
        self.assertLess(source.index('usb_vbus_sample();'), source.index('knob_apply()'))
        self.assertLess(source.index('knob_apply()'), source.index('usb_select_mode(present,proof);\n}'))
        knob = (HERE / 'knob.c').read_text(encoding='utf-8')
        for forbidden in ('GPIOD', 'PA2', 'VREFBUF', 'usb_hold'):         # HOLD, A3 and the reference stay untouched
            self.assertNotIn(forbidden, knob.split('*/', 1)[1])


class ExposureGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sector = (CAPTURE / 'capture_sector_0.bin').read_bytes()
        cls.manifest = json.loads((CAPTURE / 'manifest.json').read_text(encoding='utf-8'))

    def test_only_the_assertion_changes_and_every_checksum_holds(self):
        patched, record = gate.open_gate(self.sector, self.manifest)
        late = self.manifest['late_load']
        changed = [i for i in range(len(patched)) if patched[i] != self.sector[i]]
        self.assertEqual(changed, [27527, 27528, 27529, 27530, 27531])
        self.assertEqual(changed, record['changed_flash_offsets'])
        region = patched[late['late_flash_offset']:late['late_flash_offset'] + late['late_bytes']]
        self.assertEqual(zlib.crc32(region), late['late_crc32'])
        self.assertEqual(zlib.crc32(patched[0x2000:0x2000 + self.manifest['stage2_bytes']]),
                         int(self.manifest['stage2_crc32'], 16))
        self.assertEqual(record['address'], '0x34304b80')
        # movw r3,#1428; cmp r6,r3 are kept; beq.n becomes b.n to the same place.
        self.assertEqual(record['original'][:16], '40f294539e422fd0')
        self.assertEqual(record['patched'][:16], '40f294539e422fe0')
        self.assertEqual(record['resumes_at'], '0x34304be8')
        self.assertEqual(gate.close_gate(patched, record), self.sector)
        with self.assertRaises(ValueError):
            gate.open_gate(patched, self.manifest)                     # never applied twice

    def test_refuses_anything_but_the_reviewed_receiver(self):
        at = 27520
        absent = bytearray(self.sector); absent[at] ^= 1
        late = self.manifest['late_load']
        with self.assertRaises(ValueError):
            gate.open_gate(bytes(absent), self.manifest)               # CRC of the late range no longer matches
        relaxed = {**self.manifest, 'late_load': {**late, 'late_crc32': zlib.crc32(bytes(absent[late['late_flash_offset']:late['late_flash_offset'] + late['late_bytes']]))}}
        with self.assertRaises(ValueError):
            gate.open_gate(bytes(absent), relaxed)                     # assertion not found
        # Something branching into the bytes that would become unreachable.
        jump = bytearray(self.sector)
        source = at - 0x40                                             # b.n forward to the spare bytes
        jump[source:source + 2] = struct.pack('<H', 0xE000 | ((at + 8 - (source + 4)) // 2))
        relaxed = {**self.manifest, 'late_load': {**late, 'late_crc32': zlib.crc32(bytes(jump[late['late_flash_offset']:late['late_flash_offset'] + late['late_bytes']]))}}
        with self.assertRaises(ValueError):
            gate.open_gate(bytes(jump), relaxed)

    def test_crc_compensation_and_branch_decoder(self):
        data = bytearray(range(256)) * 3
        for offset in (0, 1, 2, 3, 100, len(data) - 4):
            for target in (0, 0xFFFFFFFF, 0x12345678, 2914057167):
                trial = bytearray(data)
                trial[offset:offset + 4] = gate.crc_compensation(bytes(trial), offset, target)
                self.assertEqual(zlib.crc32(bytes(trial)), target)
        # Decoder agrees with the reviewed B.W decoder in package.py and with known encodings.
        base = 0x34180E26
        hook = struct.pack('<HH', 0xF001, 0xB80B)
        self.assertEqual(dict(gate.branch_targets(hook, base))[base], package.branch_target(hook, base))
        self.assertEqual(dict(gate.branch_targets(bytes.fromhex('2fd0'), 0x34304B86)), {0x34304B86: 0x34304BE8})
        self.assertEqual(dict(gate.branch_targets(bytes.fromhex('84e7'), 0x34304B8A)), {0x34304B8A: 0x34304A96})
        self.assertEqual(dict(gate.branch_targets(bytes.fromhex('08b1'), 0x34304B42)), {0x34304B42: 0x34304B48})


class AdmissionTests(unittest.TestCase):
    """The committed knob package and the recovery allowlist must stay in step,
    or the park could not be verified after that package is installed."""
    PACKAGE = HERE / 'evidence/2026-11-14-knobs/package'

    def test_recovery_checker_accepts_exactly_the_committed_package(self):
        import sys
        sys.path.insert(0, str(package.ROOT / 'firmware/boot-timing'))
        recovery = load('recovery')
        spec = importlib.util.spec_from_file_location(
            'park_guard', package.ROOT / 'firmware/capture-timing/recovery_gpio/check_park.py')
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        manifest = json.loads((self.PACKAGE / 'manifest.json').read_text(encoding='utf-8'))
        pin = recovery.APPROVED[manifest['prefix_sha256']]
        self.assertEqual((pin['bytes'], pin['sector']), (manifest['prefix_bytes'], manifest['sector0_sha256']))
        self.assertEqual(manifest['hardware_status'], 'offline-only-not-installed')
        guard.APPROVED[manifest['prefix_sha256']] = dict(pin, park=0x3418078C, vcp=True)
        code, _ = guard.checked_build(self.PACKAGE / 'recovery')
        self.assertEqual(package.sha(code), manifest['prefix_sha256'])
        # The early reset path and UART guard are the installed bytes.
        installed = (HERE / 'evidence/2026-11-13-d8-hold/package/stage1.bin').read_bytes()
        hook = package.HOOK_BASE - package.PREFIX_BASE
        self.assertEqual(code[:hook], installed[:hook])
        self.assertLessEqual(len(code), package.PREFIX_END - package.PREFIX_BASE)


if __name__ == '__main__':
    unittest.main()
