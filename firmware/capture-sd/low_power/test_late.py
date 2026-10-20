"""Offline flash-boundary and actual-C late-loader CRC/ownership tests."""
from pathlib import Path
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from test_peripherals import required_defines
spec = importlib.util.spec_from_file_location("capture_sd_builder", HERE.parent / "build.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

FAKE = r"""
#pragma once
#include <stdint.h>
#include <stddef.h>
typedef struct { uint32_t CCR; } FakeScb;
typedef struct { uint32_t CYCCNT; } FakeDwt;
typedef struct { uint32_t FPCCR; } FakeFpu;
typedef struct { uint32_t AHB5ENR,AHB5RSTR; } FakeRcc;
typedef struct { uint32_t SR,CR,DCR1,DCR2,CCR,TCR,IR,FCR,DLR,AR,DR; } XSPI_TypeDef;
extern FakeScb scb; extern FakeDwt dwt; extern FakeFpu fpu; extern FakeRcc rcc;
extern XSPI_TypeDef xspi;
extern uint32_t lproof[16],sproof[16],report[128],loaded_words[2048],xspim;
extern uint32_t control,ipsr,primask,faultmask;
#define SCB (&scb)
#define DWT (&dwt)
#define FPU (&fpu)
#define RCC (&rcc)
#define XSPI1_BASE_S ((uintptr_t)&xspi)
#define XSPIM_BASE_S ((uintptr_t)&xspim)
#define SCB_CCR_DC_Msk 0x10000U
#define SCB_CCR_IC_Msk 0x20000U
#define FPU_FPCCR_LSPACT_Msk 1U
#define __get_CONTROL() control
#define __get_IPSR() ipsr
#define __get_PRIMASK() primask
#define __get_FAULTMASK() faultmask
void mock_barrier(void),mock_fail(void),mock_entry(void),mock_clear(unsigned);
uint32_t mock_status(void),mock_data(void);
#define __DSB() mock_barrier()
#define __ISB() ((void)0)
"""
HARNESS = r"""
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "under_test.c"
FakeScb scb; FakeDwt dwt; FakeFpu fpu; FakeRcc rcc; XSPI_TypeDef xspi;
uint32_t lproof[16],sproof[16],report[128],loaded_words[2048],xspim;
uint32_t control,ipsr,primask,faultmask;
static unsigned scenario,armed,got,reads,entered,red,entry_return;
static jmp_buf finish_jump;
static uint32_t card_data(unsigned at) { return 0x03020100U + 0x04040404U*(at&63U); }
void mock_clear(unsigned at) {
 assert(at>=1 && at<16 && lproof[0]==0x4C504C31U);
 lproof[at]=0;
}
void mock_barrier(void) {
 if(xspi.AR==LATE_FLASH_OFFSET && !armed) { armed=1;assert(xspi.DLR==LATE_BYTES-1); }
 if(lproof[15]) {
  assert(lproof[15]==0x4C504C44 && lproof[2]==2 && lproof[3]==0);
  assert(lproof[8]==LATE_BYTES && lproof[9]==LATE_CRC32);
 }
}
void status_led_set(unsigned state) { assert(state==4);red++; }
void mock_fail(void) { longjmp(finish_jump,1); }
void mock_entry(void) {
 assert(lproof[15]==0x4C504C44 && lproof[9]==LATE_CRC32);
 assert(!(scb.CCR&0x30000) && primask==1 && sproof[11]==1000);
 entered++;
 if(entry_return)return;
 longjmp(finish_jump,2);
}
uint32_t mock_status(void) {
 reads++;
 assert((rcc.AHB5ENR&0x2020)==0x2020 && !(rcc.AHB5RSTR&0x2020));
 if(!armed)return scenario==13?XSPI_SR_BUSY:0;
 if(scenario==15)return XSPI_SR_TEF;
 if(scenario==16)return XSPI_SR_TCF; /* Truncated before first word. */
 if(scenario==17){dwt.CYCCNT+=40000001;return XSPI_SR_BUSY;}
 if(got<LATE_BYTES/4)return XSPI_SR_BUSY|(4U<<XSPI_SR_FLEVEL_Pos);
 if(scenario==18){dwt.CYCCNT+=40000001;return XSPI_SR_BUSY;}
 if(scenario==19)return XSPI_SR_TCF|(4U<<XSPI_SR_FLEVEL_Pos);
 if(scenario==22)return XSPI_SR_TCF|XSPI_SR_TEF; /* Error after final DR. */
 return XSPI_SR_TCF;
}
uint32_t mock_data(void) {
 assert(armed && got<LATE_BYTES/4);
 uint32_t v=card_data(got++);
 return scenario==20 && got==1?v^1U:v;
}
int main(int argc,char **argv) {
 assert(argc==2);scenario=(unsigned)atoi(argv[1]);
 lproof[0]=0x4C504C31U;
 primask=1;scb.CCR=0x201;dwt.CYCCNT=100;rcc.AHB5ENR=0x2020;
 xspi.CR=0x10000001;xspi.DCR1=0x001F0000;xspi.DCR2=1;
 xspi.CCR=0x01002101;xspi.TCR=8;xspi.IR=0x0B;xspim=2;
 report[P_MAGIC]=SAVE_REPORT_MAGIC;report[P_SCHEMA]=1;report[P_WORDS]=128;
 report[P_TERMINAL]=0x444F4E45;report[P_STATE]=2;report[P_OP]=SAVE_OP_SAVE;
 report[P_MEDIA_IDLE]=1;sproof[0]=0x534C4431;sproof[7]=SAVE_CRC32;
 sproof[8]=SAVE_BYTES;sproof[11]=1000;
 switch(scenario) {
  case 0:break;case 1:control=12;break;case 2:scb.CCR|=SCB_CCR_DC_Msk;break;
  case 3:control=1;break;case 4:primask=0;break;case 5:fpu.FPCCR=1;break;
  case 6:report[P_TERMINAL]=0;break;case 7:report[P_OP]=SAVE_OP_READ;break;
  case 8:report[P_MEDIA_IDLE]=0;break;case 9:sproof[7]^=1;break;
  case 10:sproof[11]=0;break;case 11:rcc.AHB5ENR=0;break;
  case 12:rcc.AHB5RSTR=0x20;break;case 13:break;
  case 14:xspi.IR=2;break;case 15:case 16:case 17:case 18:case 19:case 20:break;
  case 21:entry_return=1;break;case 22:break;default:abort();
 }
 int jump=setjmp(finish_jump);
 if(!jump)status_led_complete_sleep();
 if(scenario<=1) {
  assert(jump==2 && entered==1 && !red && got==LATE_BYTES/4);
  for(unsigned i=0;i<LATE_BYTES/4;i++)assert(loaded_words[i]==card_data(i));
  assert(sproof[7]==SAVE_CRC32 && sproof[8]==SAVE_BYTES && sproof[11]==1000);
 } else {
  assert(jump==1 && red==1 && lproof[2]==3 && lproof[3]);
  if(scenario<15)assert(!armed && !got && !entered);
  if(scenario==20)assert(got==LATE_BYTES/4 && !entered && lproof[3]==12);
  if(scenario==21)assert(entered==1 && lproof[3]==13);
  if(scenario==22)assert(got==LATE_BYTES/4 && !entered && lproof[3]==11);
 }
 printf("scenario %u passed\n",scenario);return 0;
}
"""


class LateTests(unittest.TestCase):
    def test_ownership_published_before_legacy_completion(self):
        source = "  event(40);\n  status_led_complete_sleep();"
        result = builder.capture_save_handoff(source, True)
        for marker in ("0x4C504C31U", "0x534C4431U"):
            self.assertLess(result.index(marker), result.index("__DMB()"))
        self.assertLess(result.index("__DMB()"), result.index("event(40)"))
        self.assertLess(result.index("event(40)"), result.index("save_result=photo_save_load()"))
        self.assertNotIn("0x343F9B00", builder.capture_save_handoff(source, False))

    def test_flash_layout_boundaries(self):
        old = bytes([0xA5]) * 65536
        boot, receiver = bytes(6176), bytes(14996)
        module, late = bytes([0x71]) * 27420, bytes([0x39]) * 4096
        result = builder.pack_sector(old, boot, receiver, module, late)
        self.assertEqual(len(result), 65536)
        self.assertEqual(result[0x6000:0x6000+len(module)], module)
        self.assertEqual(result[0xE000:0xE000+len(late)], late)
        self.assertEqual(result[0x2000+len(receiver):0x6000],
                         b"\xff"*(0x4000-len(receiver)))
        self.assertEqual(result[0x6000+len(module):0xE000],
                         b"\xff"*(0x8000-len(module)))
        builder.pack_sector(old, bytes(8192), bytes(16384), bytes(32768), bytes(8192))
        for args in [
            (old, bytes(8193), receiver, module, late),
            (old, boot, bytes(16385), module, late),
            (old, boot, receiver, bytes(32772), late),
            (old, boot, receiver, module, bytes(8196)),
            (old, boot, receiver, None, late),
            (old, boot, receiver, module, bytes(3)),
        ]:
            with self.assertRaises(AssertionError):
                builder.pack_sector(*args)

    def test_actual_loader_crc_errors_and_bounds(self):
        compiler = shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(compiler)
        source = (HERE / "late_loader.c").read_text(encoding="utf-8")
        for name, value in {"LATE_PROOF":"lproof", "SAVE_PROOF":"sproof",
                            "SAVE_DONE":"report"}.items():
            source = re.sub(rf"^#define {name} .+$", f"#define {name} {value}",
                            source, flags=re.MULTILINE)
        source = source.replace("(volatile uint32_t *)LATE_LOAD_ADDRESS", "loaded_words")
        source = source.replace("LATE_PROOF[i]=0", "mock_clear(i)")
        source = source.replace("x->SR", "mock_status()").replace("x->DR", "mock_data()")
        source = re.sub(r'__asm volatile\("\.global late_completion_failure_idle.*?\);',
                        "mock_fail();", source, flags=re.S)
        source = source.replace("((void (*)(void))LATE_ENTRY_ADDRESS)();", "mock_entry();")
        with tempfile.TemporaryDirectory(prefix="camera-late-") as folder:
            work = Path(folder)
            (work/"stm32n6xx.h").write_text(
                FAKE+"\n"+required_defines(source+HARNESS), encoding="utf-8")
            (work/"status_leds.h").write_text(
                "#define STATUS_LED_ERROR 4U\nvoid status_led_set(unsigned);\n",
                encoding="utf-8")
            (work/"save_module_config.h").write_text(
                "#define SAVE_BYTES 27420U\n#define SAVE_CRC32 0xd7418a3aU\n"
                "#define SAVE_DEFAULT_MODE 1U\n#define SAVE_FLASH_OFFSET 0x6000U\n",
                encoding="utf-8")
            (work/"under_test.c").write_text(source, encoding="utf-8")
            (work/"main.c").write_text(HARNESS, encoding="utf-8")
            for size in (16,8192):
                data=bytes(v&255 for v in range(size))
                (work/"late_config.h").write_text(
                    "#define LATE_FLASH_OFFSET 0xE000U\n"
                    "#define LATE_LOAD_ADDRESS 0x343C0000U\n"
                    "#define LATE_ENTRY_ADDRESS 0x343C0001U\n"
                    f"#define LATE_BYTES {size}U\n"
                    f"#define LATE_CRC32 0x{zlib.crc32(data):08x}U\n", encoding="utf-8")
                exe=work/f"test-{size}.exe"
                subprocess.run([compiler,"-std=c11","-O2","-Wall","-Wextra",
                                "-I",str(work),"-I",str(HERE.parent),
                                str(work/"main.c"),"-o",str(exe)],check=True)
                for scenario in range(23):
                    with self.subTest(size=size,scenario=scenario):
                        subprocess.run([str(exe),str(scenario)],check=True,
                                       capture_output=True,text=True)

    def test_actual_save_loader_refuses_final_transfer_error(self):
        compiler = shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(compiler)
        source = (HERE.parent / "save_loader.c").read_text(encoding="utf-8")
        source = source.replace("(volatile uint32_t *)0x343F9E00U", "sproof")
        source = source.replace("(volatile uint32_t *)SAVE_LOAD_ADDRESS", "loaded_words")
        source = source.replace("x->SR", "mock_status()").replace("x->DR", "mock_data()")
        source = source.replace("((entry_fn)(SAVE_LOAD_ADDRESS|1U))(1U,SAVE_DEFAULT_MODE)",
                                "mock_save_entry(1U,SAVE_DEFAULT_MODE)")
        harness = r"""
#include <assert.h>
#include <stdlib.h>
#include "under_test.c"
FakeScb scb;FakeDwt dwt;FakeFpu fpu;FakeRcc rcc;XSPI_TypeDef xspi;
uint32_t lproof[16],sproof[16],report[128],loaded_words[2048],xspim;
uint32_t control,ipsr,primask,faultmask;
static unsigned scenario,armed,got,entered;
void mock_barrier(void){if(xspi.AR==SAVE_FLASH_OFFSET)armed=1;}
void status_led_set(unsigned state){assert(state==3);}
uint32_t mock_status(void){
 if(!armed)return 0;
 if(got<SAVE_BYTES/4)return XSPI_SR_BUSY|(4U<<XSPI_SR_FLEVEL_Pos);
 return XSPI_SR_TCF|(scenario?XSPI_SR_TEF:0);
}
uint32_t mock_data(void){return 0x03020100U+0x04040404U*got++;}
int mock_save_entry(uint32_t op,uint32_t mode){
 assert(op==1 && mode==1);entered++;return 0;
}
int main(int argc,char **argv){
 assert(argc==2);scenario=(unsigned)atoi(argv[1]);
 rcc.AHB5ENR=0x2020;scb.CCR=0x201;dwt.CYCCNT=100;
 xspi.CR=0x10000001;xspi.DCR1=0x001F0000;xspi.DCR2=1;
 xspi.CCR=0x01002101;xspi.TCR=8;xspi.IR=0x0B;xspim=2;
 sproof[0]=0x534C4431;
 int result=photo_save_load();
 assert(got==SAVE_BYTES/4);
 if(scenario)assert(result==-109 && entered==0 && (sproof[6]&XSPI_SR_TEF));
 else assert(result==0 && entered==1 && sproof[7]==SAVE_CRC32 && sproof[11]);
 return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="camera-save-loader-") as folder:
            work = Path(folder)
            (work/"stm32n6xx.h").write_text(
                FAKE+"\n"+required_defines(source+harness)+
                "\n#define __disable_irq() ((void)0)\n"
                "#define SCB_DisableICache() ((void)0)\n"
                "int mock_save_entry(uint32_t,uint32_t);\n", encoding="utf-8")
            (work/"status_leds.h").write_text(
                "#define STATUS_LED_NAND_WRITE 3U\nvoid status_led_set(unsigned);\n",
                encoding="utf-8")
            (work/"save_module_config.h").write_text(
                "#define SAVE_LOAD_ADDRESS 0x34320000U\n"
                "#define SAVE_FLASH_OFFSET 0x6000U\n#define SAVE_BYTES 16U\n"
                "#define SAVE_DEFAULT_MODE 1U\n"
                f"#define SAVE_CRC32 0x{zlib.crc32(bytes(range(16))):08x}U\n",
                encoding="utf-8")
            (work/"under_test.c").write_text(source, encoding="utf-8")
            (work/"main.c").write_text(harness, encoding="utf-8")
            exe=work/"test.exe"
            subprocess.run([compiler,"-std=c11","-O2","-Wall","-Wextra",
                            "-I",str(work),str(work/"main.c"),"-o",str(exe)],check=True)
            for scenario in range(2):
                subprocess.run([str(exe),str(scenario)],check=True)


if __name__ == "__main__":
    unittest.main()
