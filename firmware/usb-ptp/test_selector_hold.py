"""Run the actual selector policy and HOLD helper against a native GPIO model.

No instruments are imported. NOR loading and the terminal USB branch are
stubs; the real state decision and GPIO writes are compiled unchanged.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class SelectorHoldTests(unittest.TestCase):
    def test_usb_absent_present_ambiguous_load_fault_and_pin_refusal(self):
        compiler = shutil.which('clang') or shutil.which('gcc')
        if not compiler:
            self.skipTest('Native C compiler unavailable')
        with tempfile.TemporaryDirectory(prefix='usb-selector-hold-') as tmp:
            root = Path(tmp)
            # Remap fixed SRAM records and skip only the target BSS clear.
            # Exercise both real entries as well as their mode decisions.
            source = (HERE / 'selector.c').read_text(encoding='utf-8')
            self.assertEqual(source.count('0x343F7F00U'), 1)
            clear='for(uint32_t *p=&__bss_start__;p<&__bss_end__;p++)*p=0;'
            self.assertEqual(source.count(clear),1)
            source=source.replace(clear,'/* native BSS is already initialized */')
            source=source.replace('0x343F7F00U','(uintptr_t)request').replace('0x343F9000U','(uintptr_t)selector_proof')
            (root / 'selector.c').write_text(source, encoding='utf-8')
            shutil.copyfile(HERE / 'usb_hold.h', root / 'usb_hold.h')
            shutil.copyfile(HERE / 'capture_controls.h', root / 'capture_controls.h')
            (root / 'stm32n6xx_hal.h').write_text(r'''
#include <stdint.h>
#include <assert.h>
#include <setjmp.h>
typedef struct {uint32_t AHB4ENSR,AHB4ENR,AHB4RSTR;} MockRCC;
typedef struct {uint32_t BSRR,OTYPER,OSPEEDR,PUPDR,MODER,ODR,IDR;} MockGPIO;
typedef struct {uint32_t CYCCNT;} MockDWT;
extern MockRCC rcc; extern MockGPIO ga; extern MockDWT dwt;
extern uint32_t request[8],selector_proof[16];
#define RCC (&rcc)
#define GPIOD (&ga)
#define DWT (&dwt)
#define RCC_AHB4ENR_GPIODEN 1U
#define RCC_AHB4RSTR_GPIODRST 1U
void sync_regs(void);void park_now(void);void usb_app(void);
#define __DSB() sync_regs()
#define __ISB() ((void)0)
#define __NOP() park_now()
''', encoding='utf-8')
            (root / 'boot_read.h').write_text('int boot_read(uint32_t,uint8_t *,uint32_t,uint32_t);\n', encoding='utf-8')
            (root / 'boot_config.h').write_text('#define USB_FLASH_OFFSET 0x12000U\n#define USB_BYTES 8U\n#define USB_CRC 123U\n#define USB_ENTRY ((uintptr_t)usb_app)\n', encoding='utf-8')
            (root / 'test.c').write_text(r'''
#include "selector.c"
#include <string.h>
MockRCC rcc; MockGPIO ga; MockDWT dwt;
uint32_t request[8],selector_proof[16],__bss_start__,__bss_end__;
volatile uint32_t vbus_proof[16];
static jmp_buf terminal;
static unsigned loads,success,set_high,samples,legacy_calls;
static int cable;
#ifdef CAPTURE_CONTROLS_ENABLED
void capture_controls_sample(void){samples++;}
#define selector_entry usb_selector_body
#define direct_samples 1U
#else
volatile uint32_t knob_proof[32];
uint32_t knob_apply(void){legacy_calls++;return 0;}
#define selector_entry usb_selector
#define direct_samples 0U
#endif
int usb_vbus_sample(void){return cable;}
static int off(void){return !(ga.ODR&4096U)&&!(ga.IDR&4096U)&&
 (ga.MODER&50331648U)==16777216U&&!(ga.PUPDR&50331648U)&&!(ga.OTYPER&4096U);}
void sync_regs(void){
 rcc.AHB4ENR|=rcc.AHB4ENSR;rcc.AHB4ENSR=0;
 if(ga.BSRR&4096U)set_high++;
 ga.ODR=(ga.ODR|(ga.BSRR&65535U))&~(ga.BSRR>>16);ga.BSRR=0;
 if((ga.MODER&50331648U)==16777216U)ga.IDR=(ga.IDR&~4096U)|(ga.ODR&4096U);
}
void park_now(void){longjmp(terminal,1);}
void usb_app(void){assert(off());assert(loads==1);assert(request[0]==0x31505450U);longjmp(terminal,2);}
int boot_read(uint32_t addr,uint8_t *p,uint32_t n,uint32_t crc){
 assert(off());assert(addr==USB_FLASH_OFFSET&&n==USB_BYTES&&crc==USB_CRC);
 assert((uintptr_t)p==0x34300000U);loads++;return success;
}
static void reset(void){
 memset(&rcc,0,sizeof rcc);memset(&ga,0,sizeof ga);memset(request,0xff,sizeof request);
 ga.MODER=0xA5A5A595U;ga.PUPDR=0x5A5A5A5AU;ga.OTYPER=0xA5A5U;
 ga.OSPEEDR=0x12345678U;ga.ODR=0x5A5EU;ga.IDR=ga.ODR;
 dwt.CYCCNT=12345U;loads=0;success=1;set_high=0;samples=0;legacy_calls=0;cable=0;memset(selector_proof,0,sizeof selector_proof);
}
static void untouched_other_pins(MockGPIO before){
 assert((ga.MODER&~50331648U)==(before.MODER&~50331648U));
 assert((ga.PUPDR&~50331648U)==(before.PUPDR&~50331648U));
 assert((ga.OSPEEDR&~50331648U)==(before.OSPEEDR&~50331648U));
 assert((ga.OTYPER&~4096U)==(before.OTYPER&~4096U));
 assert((ga.ODR&~4096U)==(before.ODR&~4096U));assert(set_high==0&&samples==0);
}
int main(void){
 uint32_t proof[16]={0};
 reset();MockGPIO before=ga;usb_select_mode(0,proof);
 assert(!memcmp(&ga,&before,sizeof ga));assert(loads==0&&samples==direct_samples); /* capture alone samples, retaining HOLD */
 reset();before=ga;int ended=setjmp(terminal);
 if(!ended){usb_select_mode(1,proof);assert(0);}
 assert(ended==2&&proof[1]==4&&proof[7]==12345U&&off());untouched_other_pins(before);
 reset();before=ga;ended=setjmp(terminal);
 if(!ended){usb_select_mode(-1,proof);assert(0);}
 assert(ended==1&&proof[1]==0xE002U&&loads==0&&off());untouched_other_pins(before);
 reset();before=ga;success=0;ended=setjmp(terminal);
 if(!ended){usb_select_mode(1,proof);assert(0);}
 assert(ended==1&&proof[1]==0xE003U&&loads==1&&off());untouched_other_pins(before);
 reset();rcc.AHB4RSTR=1U;ended=setjmp(terminal);
 if(!ended){usb_select_mode(1,proof);assert(0);}
 assert(ended==1&&proof[1]==0xE005U&&loads==0&&set_high==0);
 /* The full entry calls exactly one implementation only on battery boot.
  * The unselected implementation has no definition: accidental references
  * also fail at link time, even if the smoke path would not call them. */
 reset();before=ga;selector_entry();
 assert(!memcmp(&ga,&before,sizeof ga)&&loads==0);
#ifdef CAPTURE_CONTROLS_ENABLED
 assert(samples==1&&legacy_calls==0);
#else
 assert(samples==0&&legacy_calls==1&&selector_proof[10]==0);
#endif
 for(int present=-1;present<=1;present+=2){
  reset();cable=present;ended=setjmp(terminal);
  if(!ended){selector_entry();assert(0);}
  assert(ended==(present==1?2:1)&&off()&&samples==0&&legacy_calls==0);
 }
 return 0;
}
''', encoding='utf-8')
            for profile,flags in [('default',[]),('controls',['-DCAPTURE_CONTROLS_ENABLED=1']),('legacy',['-DLEGACY_KNOBS_ENABLED=1'])]:
                with self.subTest(profile=profile):
                    exe=root/('selector-'+profile+'.exe')
                    compiled=subprocess.run([compiler,*flags,'-std=c11','-Wall','-Wextra','-Werror',
                                             '-Wno-pointer-to-int-cast','-I'+str(root),
                                             str(root/'test.c'),'-o',str(exe)],capture_output=True,text=True)
                    self.assertEqual(compiled.returncode,0,compiled.stderr)
                    result=subprocess.run([str(exe)],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            both=subprocess.run([compiler,'-DCAPTURE_CONTROLS_ENABLED=1','-DLEGACY_KNOBS_ENABLED=1',
                                 '-std=c11','-I'+str(root),str(root/'test.c'),'-o',str(root/'both.exe')],
                                capture_output=True,text=True)
            self.assertNotEqual(both.returncode,0)
            self.assertIn('never both',both.stderr)


if __name__ == '__main__':
    unittest.main()
