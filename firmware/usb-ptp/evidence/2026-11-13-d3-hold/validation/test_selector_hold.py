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
            # Only remap the request record; native tests invoke the real
            # mode decision after the target-only BSS/timer/sampler setup.
            source = (HERE / 'selector.c').read_text(encoding='utf-8')
            self.assertEqual(source.count('0x343F7F00U'), 1)
            (root / 'selector.c').write_text(source.replace('0x343F7F00U', '(uintptr_t)request'), encoding='utf-8')
            shutil.copyfile(HERE / 'usb_hold.h', root / 'usb_hold.h')
            (root / 'stm32n6xx_hal.h').write_text(r'''
#include <stdint.h>
#include <assert.h>
#include <setjmp.h>
typedef struct {uint32_t AHB4ENSR,AHB4ENR,AHB4RSTR;} MockRCC;
typedef struct {uint32_t BSRR,OTYPER,OSPEEDR,PUPDR,MODER,ODR,IDR;} MockGPIO;
typedef struct {uint32_t CYCCNT;} MockDWT;
extern MockRCC rcc; extern MockGPIO ga; extern MockDWT dwt;
extern uint32_t request[8];
#define RCC (&rcc)
#define GPIOE (&ga)
#define DWT (&dwt)
#define RCC_AHB4ENR_GPIOEEN 1U
#define RCC_AHB4RSTR_GPIOERST 1U
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
uint32_t request[8],__bss_start__,__bss_end__;
volatile uint32_t vbus_proof[16];
static jmp_buf terminal;
static unsigned loads,success,set_high;
int usb_vbus_sample(void){return 1;}
static int off(void){return !(ga.ODR&512U)&&!(ga.IDR&512U)&&
 (ga.MODER&786432U)==262144U&&!(ga.PUPDR&786432U)&&!(ga.OTYPER&512U);}
void sync_regs(void){
 rcc.AHB4ENR|=rcc.AHB4ENSR;rcc.AHB4ENSR=0;
 if(ga.BSRR&512U)set_high++;
 ga.ODR=(ga.ODR|(ga.BSRR&65535U))&~(ga.BSRR>>16);ga.BSRR=0;
 if((ga.MODER&786432U)==262144U)ga.IDR=(ga.IDR&~512U)|(ga.ODR&512U);
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
 dwt.CYCCNT=12345U;loads=0;success=1;set_high=0;
}
static void untouched_other_pins(MockGPIO before){
 assert((ga.MODER&~786432U)==(before.MODER&~786432U));
 assert((ga.PUPDR&~786432U)==(before.PUPDR&~786432U));
 assert((ga.OSPEEDR&~786432U)==(before.OSPEEDR&~786432U));
 assert((ga.OTYPER&~512U)==(before.OTYPER&~512U));
 assert((ga.ODR&~512U)==(before.ODR&~512U));assert(set_high==0);
}
int main(void){
 uint32_t proof[16]={0};
 reset();MockGPIO before=ga;usb_select_mode(0,proof);
 assert(!memcmp(&ga,&before,sizeof ga));assert(loads==0); /* capture retains HOLD */
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
 return 0;
}
''', encoding='utf-8')
            exe = root / 'selector-hold.exe'
            compiled = subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
                                       '-Wno-pointer-to-int-cast', '-I'+str(root),
                                       str(root/'test.c'), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
