"""Actual-C marker bounds, GPIO ownership and context preservation tests."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
FAKE = r'''
#pragma once
#include <stdint.h>
typedef struct { uint32_t CTRL,CYCCNT; } Dwt;
typedef struct { uint32_t DEMCR; } Debug;
typedef struct { uint32_t AHB4ENSR,AHB4ENR,AHB4RSTR; } Rcc;
typedef struct { uint32_t BSRR,OTYPER,OSPEEDR,PUPDR,MODER; } Gpio;
extern Dwt dwt; extern Debug debug; extern Rcc rcc; extern Gpio gpio;
extern uint32_t primask;
#define DWT (&dwt)
#define CoreDebug (&debug)
#define RCC (&rcc)
#define GPIOD (&gpio)
#define DWT_CTRL_CYCCNTENA_Msk 1U
#define CoreDebug_DEMCR_TRCENA_Msk (1U<<24)
#define RCC_AHB4ENSR_GPIODENS 8U
#define RCC_AHB4ENR_GPIODEN 8U
#define RCC_AHB4RSTR_GPIODRST 8U
#define __get_PRIMASK() primask
#define __disable_irq() (primask=1U)
#define __set_PRIMASK(x) (primask=(x))
uint32_t read_cycles(void);
void gpio_write(uint32_t),barrier(void);
#define __DSB() barrier()
#define __NOP() ((void)0)
'''
HARNESS = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "under_test.c"
Dwt dwt; Debug debug; Rcc rcc; Gpio gpio;
uint32_t primask,step,reads,writes,high,high_at,width,odr;
void barrier(void) { rcc.AHB4ENR |= rcc.AHB4ENSR; }
uint32_t read_cycles(void) { uint32_t v=dwt.CYCCNT;dwt.CYCCNT+=step;reads++;return v; }
void gpio_write(uint32_t v) {
 assert(v==(1U<<12) || v==(1U<<28)); writes++;
 if(v==(1U<<12)) { assert(primask==1 && !high);high=1;high_at=dwt.CYCCNT;odr|=1U<<12; }
 else { if(high) width=dwt.CYCCNT-high_at;high=0;odr&=~(1U<<12); }
}
int main(int argc,char **argv) {
 assert(argc==2);unsigned s=(unsigned)atoi(argv[1]);
 dwt.CTRL=1;debug.DEMCR=1U<<24;step=17;primask=s&1;
 gpio.MODER=0xA5A5A5A5;gpio.OTYPER=0xFFFF;gpio.PUPDR=0xA5A5A5A5;
 gpio.OSPEEDR=0x5A5A5A5A;odr=0xA5A5;
 if(s==20) dwt.CTRL=0;
 if(s==21) debug.DEMCR=0;
 if(s==22) rcc.AHB4RSTR=8;
 int init=phase_gpio_init();
 if(s>=20) { assert(!init && writes==0);return 0; }
 assert(init && writes==1 && !high);
 assert((gpio.MODER&~(3U<<24))==(0xA5A5A5A5&~(3U<<24)));
 assert((gpio.MODER&(3U<<24))==(1U<<24));
 assert((gpio.OTYPER&~(1U<<12))==(0xFFFF&~(1U<<12)));
 assert(!(gpio.PUPDR&(3U<<24)));
 assert((gpio.OSPEEDR&(3U<<24))==(1U<<24));
 uint32_t previous=primask,other=odr&~(1U<<12),event=s;
 if(s==11) event=0;
 if(s==12) event=11;
 if(s==13) {event=1;dwt.CTRL=0;}
 if(s==14) {event=10;step=0;}
 if(s==15) {event=10;dwt.CYCCNT=0xFFFFFF80;}
 int result=phase_gpio_emit(event);
 assert(primask==previous && !high && !(odr&(1U<<12)));
 assert((odr&~(1U<<12))==other);
 if(s>=11 && s<=13) assert(!result && writes==1 && reads==0);
 else if(s==14) assert(!result && writes==3 && reads==4097);
 else { assert(result && writes==3);assert(width>=event*200 && width<event*200+2*step); }
 assert(reads<=4097);return 0;
}
'''

class MarkerTests(unittest.TestCase):
    def test_actual_c_gpio_context_and_bounded_counter(self):
        compiler = shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(compiler)
        source = (HERE / "phase_gpio.c").read_text()
        source = source.replace("DWT->CYCCNT", "read_cycles()")
        source = re.sub(r"GPIOD->BSRR = ([^;]+);", r"gpio_write(\1);", source)
        with tempfile.TemporaryDirectory(prefix="camera-phase-marker-") as tmp:
            tmp = Path(tmp)
            (tmp / "stm32n6xx.h").write_text(FAKE)
            (tmp / "under_test.c").write_text(source)
            (tmp / "test.c").write_text(HARNESS)
            exe = tmp / "test.exe"
            subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                            "-I", str(tmp), "-I", str(HERE), str(tmp / "test.c"), "-o", str(exe)], check=True)
            for scenario in list(range(1,16)) + [20,21,22]:
                with self.subTest(scenario=scenario):
                    subprocess.run([str(exe), str(scenario)], check=True, capture_output=True)

if __name__ == "__main__":
    unittest.main()
