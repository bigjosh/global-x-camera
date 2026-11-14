"""Execute the actual security setup against adversarial MMIO fixtures.

This is a native build of the source block, not a second implementation of its
read/modify/write. It checks preservation and refusal paths; it does not model
the ADC analog behavior or replace the bench experiment.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class ADCSecurityRegression(unittest.TestCase):
    def test_actual_source_preserves_attributes_and_rejects_refused_configuration(self):
        source = (HERE / 'control.c').read_text()
        begin = source.index(' /* RM0486 section15.3.16:')
        end = source.index('#if defined(CONTROL_ADC_HSI8)', begin)
        block = source[begin:end]
        # The mandatory setup dominates both calibration and all conversions.
        self.assertLess(begin, source.index('if(HAL_ADC_Init'))
        self.assertLess(begin, source.index('if(HAL_ADCEx_Calibration_Start'))
        self.assertNotIn('CONTROL_ADC_SECURE', source)
        self.assertNotIn('adc-secure', (HERE / 'build.py').read_text())
        block = block.replace(
            'volatile uint32_t *security_proof=(volatile uint32_t *)0x343C2300U;',
            'volatile uint32_t *security_proof=proof;')
        self.assertNotIn('0x343C2300', block)
        harness = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#include <stdlib.h>
struct rcc_t { uint32_t AHB3ENR, AHB3ENSR; } rcc;
struct rif_t { uint32_t RISC_SECCFGRx[6], RISC_PRIVCFGRx[6]; } rif;
struct gpio_t { uint32_t SECCFGR; } ga,gf,gc,gg,gh;
#define RCC (&rcc)
#define RIFSC (&rif)
#define GPIOA (&ga)
#define GPIOF (&gf)
#define GPIOC (&gc)
#define GPIOG (&gg)
#define GPIOH (&gh)
#define RCC_AHB3ENR_RIFSCEN 0x200U
#define RCC_AHB3ENSR_RIFSCENS 0x200U
static uint32_t Q[8], proof[14], old_sec, error;
static int deny_clock,deny_security;
static jmp_buf failure;
static void barrier(void) {
 if(!deny_clock)rcc.AHB3ENR|=rcc.AHB3ENSR;
 if(deny_security)rif.RISC_SECCFGRx[2]=old_sec;
}
#define __DSB() barrier()
static void finish(uint32_t value) {error=value;longjmp(failure,1);}
static void run(void) { error=0;if(setjmp(failure))return;
BLOCK
}
static uint32_t state=0x7A69B13CU;
static uint32_t random_word(void) {state^=state<<13;state^=state>>17;state^=state<<5;return state;}
#define CHECK(x) do {if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);return 1;}}while(0)
int main(void) {
 for(unsigned trial=0;trial<4096;trial++) {
  for(unsigned i=0;i<6;i++){rif.RISC_SECCFGRx[i]=random_word();rif.RISC_PRIVCFGRx[i]=random_word();}
  ga.SECCFGR=random_word()|0x700U;gf.SECCFGR=random_word()|8U;gc.SECCFGR=random_word();gg.SECCFGR=random_word()|0x8000U;gh.SECCFGR=random_word();
  rcc.AHB3ENR=random_word();rcc.AHB3ENSR=0;
  Q[1]=random_word();old_sec=rif.RISC_SECCFGRx[2];
  struct rif_t old_rif=rif;struct gpio_t old_ga=ga,old_gf=gf,old_gc=gc,old_gg=gg,old_gh=gh;
  uint32_t old_clock=rcc.AHB3ENR;deny_clock=deny_security=0;
  run();CHECK(error==0);CHECK(proof[10]==1);CHECK(proof[11]==Q[1]);
  CHECK(rif.RISC_SECCFGRx[2]==(old_sec|1U));
  old_rif.RISC_SECCFGRx[2]|=1U;CHECK(memcmp(&rif,&old_rif,sizeof rif)==0);
  CHECK(ga.SECCFGR==old_ga.SECCFGR&&gf.SECCFGR==old_gf.SECCFGR&&gc.SECCFGR==old_gc.SECCFGR&&gg.SECCFGR==old_gg.SECCFGR&&gh.SECCFGR==old_gh.SECCFGR);
  CHECK(rcc.AHB3ENR==(old_clock|0x200U));CHECK(rcc.AHB3ENSR==0x200U);
  CHECK(proof[1]==old_sec&&proof[2]==(old_sec|1U));
  CHECK(proof[3]==proof[4]&&proof[3]==old_rif.RISC_PRIVCFGRx[2]);
 }
 for(unsigned missing=0;missing<5;missing++) {
  ga.SECCFGR=gf.SECCFGR=gc.SECCFGR=gg.SECCFGR=gh.SECCFGR=0xffffU;
  if(missing<3)ga.SECCFGR&=~(1U<<(8+missing));
  else if(missing==3)gf.SECCFGR&=~8U;else gg.SECCFGR&=~0x8000U;
  old_sec=rif.RISC_SECCFGRx[2]=0xabc00000U;run();
  CHECK(error==21&&rif.RISC_SECCFGRx[2]==old_sec&&proof[10]==0);
 }
 ga.SECCFGR=gf.SECCFGR=gc.SECCFGR=gg.SECCFGR=gh.SECCFGR=0xffffU;
 old_sec=rif.RISC_SECCFGRx[2]=0x55aa0000U;deny_security=1;run();
 CHECK(error==22&&rif.RISC_SECCFGRx[2]==old_sec&&proof[10]==0);
 deny_security=0;deny_clock=1;rcc.AHB3ENR=0;rcc.AHB3ENSR=0;run();
 CHECK(error==20&&rif.RISC_SECCFGRx[2]==old_sec&&proof[10]==0);
 puts("4096 preserved-state cases and 7 refusal cases passed");return 0;
}
'''.replace('BLOCK', block)
        compiler = shutil.which('clang') or shutil.which('gcc')
        self.assertIsNotNone(compiler, 'A native C compiler is required for this regression')
        with tempfile.TemporaryDirectory(prefix='control-adc-security-') as folder:
            folder = Path(folder)
            c = folder / 'check.c'
            exe = folder / 'check.exe'
            c.write_text(harness)
            subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(exe)], check=True)
            result = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
            self.assertIn('4096 preserved-state cases and 7 refusal cases passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
