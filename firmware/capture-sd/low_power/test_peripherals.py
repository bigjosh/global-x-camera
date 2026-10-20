"""Offline execution of the actual teardown C, with modeled register banks.

The model rejects every CSI/DCMIPP/I2C/XSPI access without its clocks/reset
qualification, including after teardown. It is not an analog power or GPIO
transition proof; those remain hardware measurements.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CMSIS = ROOT / "tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers/CMSIS/Device/ST/STM32N6xx/Include/stm32n657xx.h"

FAKE = r"""
#pragma once
#include <stdint.h>
#include <stddef.h>
typedef struct {
 uint32_t APB4ENR2,APB5ENR,APB5RSTR,DIVENR,APB1ENR1,APB1RSTR1;
 uint32_t AHB5ENR,AHB5RSTR,AHB4ENR,AHB4RSTR;
 uint32_t APB5RSTSR,APB5ENCR,APB5LPENCR,DIVENCR,APB1RSTSR1;
 uint32_t APB1ENCR1,APB1LPENCR1,AHB5RSTSR,AHB5ENCR,AHB5LPENCR;
} FakeRcc;
typedef struct { uint32_t MODER,OTYPER,OSPEEDR,PUPDR,IDR,ODR,BSRR,AFR[2]; } FakeGpio;
typedef struct { uint32_t SR0,SR1,CR,PCR,PRCR,IER0,IER1; } FakeCsi;
typedef struct {
 uint32_t CMSR1,P0FCTCR,P1FCTCR,P2FCTCR,P0FSCR,P1FSCR,P2FSCR;
 uint32_t CMIER,P0IER,P1IER,P2IER;
} FakeDcmipp;
typedef struct { uint32_t ISR,CR1; } FakeI2c;
typedef struct { uint32_t SR,CR,DCR1,DCR2,CCR,TCR,IR; } XSPI_TypeDef;
typedef struct { uint32_t CCR; } FakeScb;
typedef struct { uint32_t CYCCNT; } FakeDwt;
typedef struct { uint32_t FPCCR; } FakeFpu;
extern FakeRcc fake_rcc;
extern FakeScb fake_scb;
extern FakeDwt fake_dwt;
extern FakeFpu fake_fpu;
extern FakeCsi fake_csi;
extern FakeDcmipp fake_dcmipp;
extern FakeI2c fake_i2c;
extern XSPI_TypeDef fake_xspi;
extern FakeGpio fake_b,fake_c,fake_n,fake_o;
extern uint32_t fake_report[128],fake_loader[16],fake_dataoff[16];
extern uint32_t fake_control,fake_ipsr,fake_primask,fake_faultmask,fake_xspim;
extern _Alignas(8) unsigned char fake_card_bytes[200],fake_fs_bytes[80];
FakeCsi *checked_csi(void);
FakeDcmipp *checked_dcmipp(void);
FakeI2c *checked_i2c(void);
XSPI_TypeDef *checked_xspi(void);
uint32_t *checked_xspim(void);
FakeGpio *checked_gpio(FakeGpio *,uint32_t);
void mock_barrier(void);
#define RCC (&fake_rcc)
#define SCB (&fake_scb)
#define DWT (&fake_dwt)
#define FPU (&fake_fpu)
#define CSI checked_csi()
#define DCMIPP checked_dcmipp()
#define I2C2 checked_i2c()
#define GPIOB checked_gpio(&fake_b,RCC_AHB4ENR_GPIOBEN)
#define GPIOC checked_gpio(&fake_c,RCC_AHB4ENR_GPIOCEN)
#define GPION checked_gpio(&fake_n,RCC_AHB4ENR_GPIONEN)
#define GPIOO checked_gpio(&fake_o,RCC_AHB4ENR_GPIOOEN)
#define XSPI1_BASE_S ((uintptr_t)&fake_xspi)
#define XSPIM_BASE_S ((uintptr_t)checked_xspim())
#define SCB_CCR_DC_Msk 0x10000U
#define SCB_CCR_IC_Msk 0x20000U
#define FPU_FPCCR_LSPACT_Msk 1U
#define __get_CONTROL() fake_control
#define __get_IPSR() fake_ipsr
#define __get_PRIMASK() fake_primask
#define __get_FAULTMASK() fake_faultmask
#define __DSB() mock_barrier()
"""

HARNESS = r"""
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "under_test.c"
FakeRcc fake_rcc;
FakeScb fake_scb;
FakeDwt fake_dwt;
FakeFpu fake_fpu;
FakeCsi fake_csi;
FakeDcmipp fake_dcmipp;
FakeI2c fake_i2c;
XSPI_TypeDef fake_xspi;
FakeGpio fake_b,fake_c,fake_n,fake_o;
uint32_t fake_report[128],fake_loader[16],fake_dataoff[16];
uint32_t fake_control,fake_ipsr,fake_primask,fake_faultmask,fake_xspim;
_Alignas(8) unsigned char fake_card_bytes[200],fake_fs_bytes[80];
static unsigned scenario,peripheral_accesses,clock_writes;
static camera_peripheral_proof_t proof;
static void gpio_effect(FakeGpio *g) {
 g->ODR |= g->BSRR & 65535U;
 g->ODR &= ~(g->BSRR >> 16);
 g->BSRR=0;
 for(unsigned p=0;p<16;p++) if(((g->MODER>>(2*p))&3U)==1U) {
  g->IDR=(g->IDR&~(1U<<p)) | (g->ODR&(1U<<p));
 }
 if(scenario==36 && g==&fake_o) g->IDR|=1U<<5;
 if(scenario==43 && g==&fake_n) g->IDR&=~(1U<<1);
}
void mock_barrier(void) {
 #define SET_CLEAR(field,reg,set) do { \
  if(fake_rcc.field) { \
   if(set) fake_rcc.reg |= fake_rcc.field; \
   else fake_rcc.reg &= ~fake_rcc.field; \
   fake_rcc.field=0; clock_writes++; \
  } } while(0)
 SET_CLEAR(APB5RSTSR,APB5RSTR,1);
 SET_CLEAR(APB5ENCR,APB5ENR,0);
 SET_CLEAR(DIVENCR,DIVENR,0);
 SET_CLEAR(APB1RSTSR1,APB1RSTR1,1);
 SET_CLEAR(APB1ENCR1,APB1ENR1,0);
 SET_CLEAR(AHB5RSTSR,AHB5RSTR,1);
 SET_CLEAR(AHB5ENCR,AHB5ENR,0);
 #undef SET_CLEAR
 gpio_effect(&fake_b); gpio_effect(&fake_c);
 gpio_effect(&fake_n); gpio_effect(&fake_o);
 fake_dwt.CYCCNT++;
 if(proof.word[LP_TERMINAL]==CAMERA_PERIPHERAL_DONE) {
  assert(proof.word[LP_STATE]==2 && proof.word[LP_RESULT]==0);
  assert(off_state());
 }
}
FakeCsi *checked_csi(void) {
 peripheral_accesses++;
 assert((fake_rcc.APB5ENR&RCC_APB5ENR_CSIEN) &&
        !(fake_rcc.APB5RSTR&RCC_APB5RSTR_CSIRST) &&
        (fake_rcc.DIVENR&RCC_DIVENR_IC18EN));
 return &fake_csi;
}
FakeDcmipp *checked_dcmipp(void) {
 peripheral_accesses++;
 assert((fake_rcc.APB5ENR&RCC_APB5ENR_DCMIPPEN) &&
        !(fake_rcc.APB5RSTR&RCC_APB5RSTR_DCMIPPRST) &&
        (fake_rcc.DIVENR&RCC_DIVENR_IC17EN));
 return &fake_dcmipp;
}
FakeI2c *checked_i2c(void) {
 peripheral_accesses++;
 assert((fake_rcc.APB1ENR1&RCC_APB1ENR1_I2C2EN) &&
        !(fake_rcc.APB1RSTR1&RCC_APB1RSTR1_I2C2RST));
 return &fake_i2c;
}
XSPI_TypeDef *checked_xspi(void) {
 peripheral_accesses++;
 assert((fake_rcc.AHB5ENR&NOR_BUS)==NOR_BUS &&
        !(fake_rcc.AHB5RSTR&(RCC_AHB5RSTR_XSPI1RST|RCC_AHB5RSTR_XSPIMRST)));
 return &fake_xspi;
}
uint32_t *checked_xspim(void) {
 (void)checked_xspi(); return &fake_xspim;
}
FakeGpio *checked_gpio(FakeGpio *g,uint32_t bit) {
 assert((fake_rcc.AHB4ENR&bit) && !(fake_rcc.AHB4RSTR&bit)); return g;
}
int main(int argc,char **argv) {
 assert(argc==2); scenario=(unsigned)atoi(argv[1]);
 sd_card_t *c=(sd_card_t *)fake_card_bytes;
 photo_fs_report_t *f=(photo_fs_report_t *)fake_fs_bytes;
 uint32_t *r=fake_report,*l=fake_loader;
 fake_primask=1; fake_scb.CCR=0x201; fake_dwt.CYCCNT=100;
 r[P_MAGIC]=SAVE_REPORT_MAGIC; r[P_SCHEMA]=1;r[P_WORDS]=128;
 r[P_TERMINAL]=0x444F4E45; r[P_STATE]=2;r[P_OP]=SAVE_OP_SAVE;
 r[P_MODE]=SAVE_DEFAULT_MODE;r[P_STAGE]=8;r[P_MEDIA_IDLE]=1;
 r[P_FINAL_CCR]=0x201;r[P_POSTCLEAN_VALIDATED]=1;
 r[P_FNV_BEFORE]=r[P_FNV_AFTER]=r[P_POSTCLEAN_FNV]=123;
 r[P_WIDTH]=SAVE_WIDTH;r[P_HEIGHT]=SAVE_HEIGHT;r[P_FRAME_BYTES]=SAVE_FRAME_BYTES;
 r[P_CARD_SIZE]=sizeof(*c);r[P_FS_SIZE]=sizeof(*f);r[P_PNG_BYTES_LO]=1234;
 l[0]=0x534C4431;l[7]=SAVE_CRC32;l[8]=SAVE_BYTES;l[11]=1000;
 c->media_idle=1;c->stage=SD_STAGE_DEINIT;c->last_ready_r1=0x900;c->sector_count=100000;
 f->state=PHOTO_FS_STATE_FINISHED;f->stage=PHOTO_FS_STAGE_RENAME;
 f->completed=1;f->bytes_written=1234;f->sector_count=c->sector_count;
 fake_dataoff[0]=0x46534431;fake_dataoff[1]=1;fake_dataoff[2]=4;fake_dataoff[12]=3;
 fake_rcc.APB4ENR2=RCC_APB4ENR2_BSECEN|0x80000000U;
 fake_rcc.APB5ENR=CAMERA_BUS|0x80000000U;fake_rcc.DIVENR=CAMERA_KERNEL|(1U<<10);
 fake_rcc.APB1ENR1=RCC_APB1ENR1_I2C2EN|0x80000000U;
 fake_rcc.AHB5ENR=NOR_BUS|0x400U;fake_rcc.AHB4ENR=GPIO_BUS;
 fake_csi.PCR=3;fake_csi.PRCR=CSI_PRCR_PEN;fake_csi.CR=CSI_CR_CSIEN;
 fake_i2c.CR1=I2C_CR1_PE;fake_xspi.CR=0x10000001;
 fake_xspi.DCR1=0x001F0000;fake_xspi.DCR2=1;fake_xspi.CCR=0x01002101;
 fake_xspi.TCR=8;fake_xspi.IR=0x0B;fake_xspim=2;
 fake_o.MODER=1U<<10;fake_o.IDR=fake_o.ODR=1U<<5;
 fake_n.MODER=NOR_MODE_AF;fake_n.IDR=1U<<1;fake_n.AFR[0]=NOR_AF9;
 fake_b.MODER=I2C_MODE_AF;fake_c.IDR=1U<<4;
 switch(scenario) {
  case 0:case 1:case 37:case 38:case 39:case 40:case 41:case 42:break;
  case 2:fake_scb.CCR|=SCB_CCR_DC_Msk;break;
  case 3:fake_scb.CCR|=SCB_CCR_IC_Msk;break;
  case 4:fake_control=1;break;
  case 5:fake_control=2;break;
  case 6:fake_ipsr=3;break;
  case 7:fake_primask=0;break;
  case 8:fake_faultmask=1;break;
  case 9:fake_fpu.FPCCR=1;break;
  case 10:r[P_TERMINAL]=0;break;
  case 11:r[P_RESULT]=1;break;
  case 12:r[P_NONCE]=1;break;
  case 13:l[7]^=1;break;
  case 14:l[11]=0;break;
  case 15:c->media_idle=0;break;
  case 16:c->controller_owned=1;break;
  case 17:c->cleanup_error=1;break;
  case 18:c->last_ready_r1=0xE00;break;
  case 19:f->completed=0;break;
  case 20:f->bytes_written++;break;
  case 21:fake_dataoff[2]=3;break;
  case 22:fake_rcc.APB5ENR&=~RCC_APB5ENR_CSIEN;break;
  case 23:fake_rcc.APB5RSTR|=RCC_APB5RSTR_CSIRST;break;
  case 24:fake_rcc.DIVENR&=~RCC_DIVENR_IC18EN;break;
  case 25:fake_rcc.APB1ENR1&=~RCC_APB1ENR1_I2C2EN;break;
  case 26:fake_rcc.AHB5ENR&=~RCC_AHB5ENR_XSPI1EN;break;
  case 27:fake_rcc.AHB5ENR|=RCC_AHB5ENR_SDMMC2EN;break;
  case 28:fake_rcc.AHB5ENR|=RCC_AHB5ENR_XSPI2EN;break;
  case 29:fake_rcc.APB4ENR2&=~RCC_APB4ENR2_BSECEN;break;
  case 30:fake_csi.SR0=CSI_SR0_VC0STATEF;break;
  case 31:fake_dcmipp.P2FCTCR=DCMIPP_P2FCTCR_CPTREQ;break;
  case 32:fake_i2c.ISR=I2C_ISR_BUSY;break;
  case 33:fake_xspi.SR=XSPI_SR_BUSY;break;
  case 34:case 43:fake_n.IDR=0;break;
  case 35:fake_c.IDR=0;break;
  case 36:break; /* Sensor reset pin physically stuck HIGH. */
  default:abort();
 }
 if(scenario==1) fake_control=0x0C;
 if(scenario==42) fake_control=4;
 int result=camera_peripherals_shutdown(&proof);
 if(scenario<=1 || scenario==34 || (scenario>=37 && scenario<=42)) {
  assert(result==0 && proof.word[LP_TERMINAL]==CAMERA_PERIPHERAL_DONE);
  assert(fake_control==(scenario==1?12U:scenario==42?4U:0U));
  assert(fake_rcc.APB4ENR2==(RCC_APB4ENR2_BSECEN|0x80000000U));
  assert(fake_rcc.DIVENR==(1U<<10)); /* IC11 retained. */
  assert(fake_rcc.APB5ENR==0x80000000U && fake_rcc.APB1ENR1==0x80000000U);
  assert(fake_rcc.AHB5ENR==0x400U); /* Unrelated memory/cache clock retained. */
  if(scenario==34) {
   assert(!(proof.word[LP_NOR_IDR]&(1U<<1))); /* Initial AF read was LOW. */
   assert(proof.word[LP_NOR_IDR_OFF]&(1U<<1)); /* GPIO takeover is HIGH. */
  }
  unsigned count=peripheral_accesses,writes=clock_writes;
  if(scenario==37) fake_rcc.APB5ENR|=RCC_APB5ENR_CSIEN;
  if(scenario==38) fake_o.IDR|=1U<<5;
  if(scenario==39) fake_loader[11]++;
  if(scenario==40) proof.word[LP_STATE]=3;
  if(scenario==41) fake_report[P_RESULT]=1;
  result=camera_peripherals_shutdown(&proof);
  assert(peripheral_accesses==count && clock_writes==writes);
  if(scenario>=37 && scenario<=41) assert(result!=0);
  else assert(result==0 && proof.word[LP_REPEAT_COUNT]==1);
 } else {
  assert(result!=0 && proof.word[LP_TERMINAL]!=CAMERA_PERIPHERAL_DONE);
  if(scenario<36) assert(!proof.word[LP_MUTATION_STARTED] && clock_writes==0);
  else {
   assert(proof.word[LP_MUTATION_STARTED]);
   if(scenario==43) {
    assert(proof.word[LP_STAGE]==6 && result==CAMERA_PERIPHERAL_READBACK_FAILED);
    assert(fake_xspi.CR==0x10000001); /* XSPI still enabled. */
    assert((fake_n.MODER&((3U<<4)|(3U<<12)))==((2U<<4)|(2U<<12)));
    assert((fake_n.ODR&((1U<<1)|(1U<<2)|(1U<<6)))==(1U<<1));
    assert((fake_rcc.AHB5ENR&NOR_BUS)==NOR_BUS); /* No NOR gating. */
   }
   unsigned count=peripheral_accesses;
   assert(camera_peripherals_shutdown(&proof)==CAMERA_PERIPHERAL_BAD_PROOF);
   assert(peripheral_accesses==count);
  }
 }
 printf("scenario %u passed\n",scenario);return 0;
}
"""


def required_defines(source):
    definitions = {}
    for line in CMSIS.read_text(encoding="utf-8").splitlines():
        match = re.match(r"#define\s+(\w+)\s+(.+)", line)
        if match:
            definitions[match[1]] = match[2].split("/*")[0].strip()
    needed = set()
    def add(name):
        if name in definitions and name not in needed:
            needed.add(name)
            for child in re.findall(r"\b[A-Za-z_]\w*\b", definitions[name]):
                add(child)
    for name in re.findall(r"\b(?:RCC|CSI|DCMIPP|XSPI|I2C)_\w+\b", source):
        add(name)
    return "\n".join(f"#define {name} {definitions[name]}" for name in sorted(needed))


class PeripheralTests(unittest.TestCase):
    def test_guards_order_and_idempotency(self):
        compiler = shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(compiler, "Host C compiler required")
        source = (HERE / "peripherals.c").read_text(encoding="utf-8")
        bindings = {
            "SAVE_REPORT": "((volatile const uint32_t *)fake_report)",
            "LOADER_REPORT": "((volatile const uint32_t *)fake_loader)",
            "CARD_REPORT": "((volatile const sd_card_t *)fake_card_bytes)",
            "FS_REPORT": "((volatile const photo_fs_report_t *)fake_fs_bytes)",
            "DATA_OFF_REPORT": "((volatile const uint32_t *)fake_dataoff)",
        }
        for name, value in bindings.items():
            source = re.sub(rf"^#define {name} .+$", f"#define {name} {value}",
                            source, flags=re.MULTILINE)
        # Register ownership checks instrument pointer access, not driver flow.
        source = source.replace("x->", "checked_xspi()->")
        with tempfile.TemporaryDirectory(prefix="camera-peripherals-") as folder:
            work = Path(folder)
            (work / "stm32n6xx.h").write_text(
                FAKE + "\n" + required_defines(source + HARNESS), encoding="utf-8")
            (work / "save_module_config.h").write_text(
                "#define SAVE_BYTES 27420U\n#define SAVE_CRC32 0xd7418a3aU\n"
                "#define SAVE_DEFAULT_MODE 1U\n", encoding="utf-8")
            (work / "under_test.c").write_text(source, encoding="utf-8")
            (work / "main.c").write_text(HARNESS, encoding="utf-8")
            exe = work / "test.exe"
            subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra",
                            "-Wno-unused-variable", "-I", str(work),
                            "-I", str(HERE), "-I", str(HERE.parent),
                            "-I", str(ROOT / "firmware/sd-storage"),
                            str(work / "main.c"), "-o", str(exe)], check=True)
            for scenario in range(44):
                with self.subTest(scenario=scenario):
                    subprocess.run([str(exe), str(scenario)], check=True,
                                   capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
