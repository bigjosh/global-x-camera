"""Offline register-model guards and real Cortex-M55 HOLD instruction audit.

No debugger, USB device, reset, or power API is imported. The model exercises
the actual shutdown C control flow, using bit definitions exported by the
installed target CMSIS headers. It cannot prove silicon behavior, rail order,
or successful Standby entry. The linked ARM audit separately binds the exact
release/WFI/reassert machine bytes to the reviewed capture implementation.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'firmware/capture-timing'))
from build_raw10 import TC
# Independent PA2/A3 release/WFI/reassert instruction oracle. The November 8
# frozen evidence remains the PD7 implementation; schema 2 identifies PA2.
# Keep this local so the USB audit does not share its implementation oracle.
STANDBY_OPCODES = bytes.fromhex(
    '40f20000c5f20260d0f80c1021f03001c0f80c10d0f8001021f03001c0f80010'
    'bff34f8fbff36f8f30bf4ff00401c0f81810d0f8001021f0300141f01001'
    'c0f80010bff34f8f')

OUT = ROOT / 'tmp/usb-shutdown-offline'
CMSIS = ROOT / 'tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers/CMSIS'
FLAGS = ['-mcpu=cortex-m55', '-mthumb', '-mcmse', '-mfloat-abi=soft',
         '-mgeneral-regs-only', '-Os', '-ffreestanding', '-fno-builtin',
         '-fno-stack-protector', '-ffunction-sections', '-fdata-sections',
         '-Wall', '-Wextra', '-Werror', '-DSTM32N657xx',
         '-I' + str(CMSIS / 'Include'),
         '-I' + str(CMSIS / 'Device/ST/STM32N6xx/Include')]


def run(args):
    p = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=30)
    if p.returncode:
        raise RuntimeError(p.stdout + p.stderr)
    return p.stdout


def make_platform(macros):
    src = (HERE / 'shutdown.c').read_text()
    members = {}
    for obj, field in re.findall(r'\b([A-Za-z][A-Za-z0-9]*)->([A-Za-z0-9]+)', src):
        members.setdefault(obj, set()).add(field)
    gpio = set().union(*(v for k, v in members.items() if k.startswith('GPIO')))
    # Extra model state is used to observe rather than emulate source logic.
    gpio |= {'ODR', 'IDR', 'BSRR', 'MODER', 'PUPDR', 'OTYPER'}
    members.setdefault('GPIOD', set())  # historical HOLD bank must be untouched
    members['RCC'] |= {'AHB5LPENR'}
    for name in members:
        if name.startswith('GPIO'):
            members[name] = gpio
    lines = ['#ifndef USB_SHUTDOWN_TEST_PLATFORM_H', '#define USB_SHUTDOWN_TEST_PLATFORM_H',
             '#include <stdint.h>']
    for line in macros.splitlines():
        if re.match(r'#define (RCC_|PWR_|SCB_|FPU_|ICB_|DBGMCU_)', line):
            lines.append(line)
    for name, fields in sorted(members.items()):
        declarations = []
        for field in sorted(fields):
            length = 16 if name == 'NVIC' else (128 if name == 'BSEC' else 0)
            declarations.append('volatile uint32_t ' + field + (f'[{length}]' if length else '') + ';')
        lines += ['typedef struct {' + ''.join(declarations) + '} fake_' + name + ';',
                  'extern fake_' + name + ' mock_' + name + ';',
                  '#define ' + name + ' (&mock_' + name + ')']
    lines += ['extern uint32_t mock_control,mock_ipsr,mock_faultmask,mock_primask;',
              'void __DSB(void);', 'static inline void __DMB(void){}',
              'static inline void __ISB(void){}',
              'static inline void __disable_irq(void){mock_primask=1;}',
              'static inline uint32_t __get_CONTROL(void){return mock_control;}',
              'static inline uint32_t __get_IPSR(void){return mock_ipsr;}',
              'static inline uint32_t __get_FAULTMASK(void){return mock_faultmask;}',
              'static inline uint32_t __get_PRIMASK(void){return mock_primask;}',
              'void usb_shutdown_test_park(void) __attribute__((noreturn));',
              'void usb_shutdown_test_hold_wfi(void);', '#endif']
    definitions = '\n'.join('fake_' + name + ' mock_' + name + ';' for name in sorted(members))
    clears = '\n'.join('memset(&mock_' + name + ',0,sizeof(mock_' + name + '));' for name in sorted(members))
    return '\n'.join(lines) + '\n', definitions, clears


HARNESS = r'''
#include "shutdown_test_platform.h"
#include "shutdown.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
#include <stddef.h>
DEFINITIONS
uint32_t mock_control,mock_ipsr,mock_faultmask,mock_primask;
static jmp_buf terminal;
static int fault,wfi_return,wfi_count;
static unsigned asserts;
#define CHECK(x) do{asserts++;if(!(x)){fprintf(stderr,"check failed line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static void gpio(volatile uint32_t *bsrr,volatile uint32_t *odr,volatile uint32_t *idr,uint32_t moder){
 *odr=(*odr|(*bsrr&65535U))&~(*bsrr>>16);*bsrr=0;
 for(unsigned i=0;i<16;i++)if(((moder>>(i*2))&3)==1){*idr=(*idr&~(1U<<i))|(*odr&(1U<<i));}
}
void __DSB(void){
 RCC->AHB4ENR|=RCC->AHB4ENSR;RCC->AHB4ENSR=0;
 RCC->APB4ENR2|=RCC->APB4ENSR2;RCC->APB4ENSR2=0;
 RCC->AHB5RSTR|=RCC->AHB5RSTSR;RCC->AHB5RSTSR=0;
 RCC->AHB5ENR&=~RCC->AHB5ENCR;RCC->AHB5ENCR=0;
 RCC->AHB5LPENR&=~RCC->AHB5LPENCR;RCC->AHB5LPENCR=0;
 RCC->STOPCR&=~RCC->STOPCCR;RCC->STOPCCR=0;
 if(PWR->WKUPCR)PWR->WKUPSR=0;PWR->WKUPCR=0;
 for(unsigned i=0;i<16;i++){NVIC->ISER[i]&=~NVIC->ICER[i];NVIC->ISPR[i]&=~NVIC->ICPR[i];NVIC->ICER[i]=0;NVIC->ICPR[i]=0;}
 EXTI->RPR1=EXTI->RPR2=EXTI->RPR3=EXTI->FPR1=EXTI->FPR2=EXTI->FPR3=0;
 #define GPIO_APPLY(g) gpio(&g->BSRR,&g->ODR,&g->IDR,g->MODER)
 GPIO_APPLY(GPIOB);GPIO_APPLY(GPIOC);GPIO_APPLY(GPIOA);GPIO_APPLY(GPIOE);
 GPIO_APPLY(GPIOG);GPIO_APPLY(GPION);GPIO_APPLY(GPIOO);
 if(fault==1)RCC->APB4ENR2&=~RCC_APB4ENR2_BSECEN;
 if(fault==2)RCC->AHB4ENR&=~RCC_AHB4ENR_PWREN;
 if(fault==3)GPIOA->IDR&=~(1U<<2);
 if(fault==4)GPION->IDR&=~(1U<<1);
 if(fault==5)RCC->AHB5ENR|=RCC_AHB5ENR_OTG1EN;
 if(fault==6)DBGMCU->CR|=DBGMCU_CR_DBG_STANDBY;
 if(fault==7)NVIC->ISPR[0]=1;
 if(fault==8)EXTI->RPR1=1;
 if(fault==9)PWR->CPUCR&=~PWR_CPUCR_PDDS;
 if(fault==10)PWR->WKUPSR=1;
 if(fault==11)RCC->STOPCR|=RCC_STOPCR_HSISTOPEN;
}
void usb_shutdown_test_park(void){longjmp(terminal,1);}
void usb_shutdown_test_hold_wfi(void){
 CHECK(usb_shutdown_proof.state==USB_SHUTDOWN_ARMED);
 CHECK(usb_shutdown_proof.error==0 && usb_shutdown_proof.trial_entry_proven==0);
 CHECK(mock_primask==1 && (SCB->SCR&SCB_SCR_SLEEPDEEP_Msk));
 GPIOA->PUPDR&=~(3U<<4);GPIOA->MODER&=~(3U<<4);__DSB();
 CHECK(GPIOA->ODR&(1U<<2));wfi_count++;
 if(!wfi_return)longjmp(terminal,2);
 GPIOA->BSRR=1U<<2;GPIOA->MODER=(GPIOA->MODER&~(3U<<4))|(1U<<4);__DSB();
}
static void init(void){
 CLEARS
 mock_control=mock_ipsr=mock_faultmask=mock_primask=0;fault=wfi_return=wfi_count=0;
 RCC->AHB4ENR=RCC_AHB4ENR_GPIOAEN;
 RCC->MISCENR=RCC_MISCENR_DBGEN;
 RCC->AHB5ENR=RCC_AHB5ENR_OTG1EN|RCC_AHB5ENR_OTGPHY1EN|RCC_AHB5ENR_XSPI1EN|RCC_AHB5ENR_XSPIMEN;
 RCC->AHB5LPENR=RCC->AHB5ENR;
 BSEC->SFSRx[3]=BSEC->OTPVLDRx[3]=1U<<28;
 DBGMCU->CR=DBGMCU_CR_DBG_SLEEP|DBGMCU_CR_DBG_STOP|DBGMCU_CR_DBG_STANDBY|0x80000000U;
 PWR->SVMCR3=PWR_SVMCR3_USB33SV|PWR_SVMCR3_USB33VMEN|PWR_SVMCR3_ASV;
 PWR->CR4=PWR_CR4_TCMRBSEN|PWR_CR4_TCMFLXRBSEN|0x80000000U;
 PWR->CPUCR=PWR_CPUCR_SVOS|0x80000000U;
 GPIOE->MODER=0xA5555555U;GPIOE->PUPDR=0x5AAAAAAAU;GPIOE->ODR=0x1234;
 GPIOA->MODER=0xA5555555U;GPIOA->PUPDR=0x5AAAAAAAU;GPIOA->ODR=0x1234;
 GPIOD->MODER=0x13579BDFU;GPIOD->PUPDR=0x2468ACE0U;GPIOD->ODR=0x1234;
 ICB->ICTR=3;for(unsigned i=0;i<4;i++){NVIC->ISER[i]=~0U;NVIC->ISPR[i]=~0U;}
 SysTick->CTRL=7;
}
static void check_proof(void){
 const volatile uint32_t *p=(const volatile uint32_t *)&usb_shutdown_proof;
 uint32_t hash=2166136261U;
 for(unsigned i=0;i<offsetof(usb_shutdown_proof_t,checksum)/4;i++)
  for(unsigned b=0;b<4;b++)hash=(hash^((p[i]>>(b*8))&255U))*16777619U;
 CHECK(usb_shutdown_proof.magic==USB_SHUTDOWN_MAGIC);
 CHECK(usb_shutdown_proof.schema==2 && usb_shutdown_proof.words==sizeof(usb_shutdown_proof)/4);
 CHECK(usb_shutdown_proof.seal==USB_SHUTDOWN_SEAL && usb_shutdown_proof.checksum==hash);
 CHECK(usb_shutdown_proof.trial_entry_proven==0);
}
static void execute(unsigned flags,unsigned error){
 int exit_kind=setjmp(terminal);
 if(!exit_kind)usb_shutdown_enter(flags);
 check_proof();CHECK(usb_shutdown_proof.error==error);
 if(!error){
  CHECK(exit_kind==2 && wfi_count==1 && usb_shutdown_proof.state==USB_SHUTDOWN_ARMED);
  CHECK((GPIOA->MODER&(3U<<4))==0 && (GPIOA->PUPDR&(3U<<4))==0);
  CHECK((GPIOE->MODER&~(3U<<8))==(0xA5555555U&~(3U<<8)));
  CHECK((GPIOE->PUPDR&~(3U<<8))==(0x5AAAAAAAU&~(3U<<8)));
  CHECK((GPIOA->MODER&~(3U<<4))==(0xA5555555U&~(3U<<4)));
  CHECK(DBGMCU->CR==0x80000000U && PWR->SVMCR3==PWR_SVMCR3_ASV);
  CHECK(PWR->CR4==0x80000000U);
 }else{
  CHECK(exit_kind==1);
  CHECK((GPIOA->MODER&(3U<<4))==(1U<<4));CHECK(GPIOA->ODR&(1U<<2));
  CHECK(!(SCB->SCR&SCB_SCR_SLEEPDEEP_Msk));
  CHECK(wfi_count==(error==USB_SHUTDOWN_UNEXPECTED_RETURN?1:0));
  CHECK(usb_shutdown_proof.state==(error==USB_SHUTDOWN_UNEXPECTED_RETURN?USB_SHUTDOWN_RETURNED:USB_SHUTDOWN_REFUSED));
 }
 CHECK(!(RCC->AHB5RSTR&RCC_AHB5RSTR_SDMMC2RST));
 CHECK(GPIOD->MODER==0x13579BDFU && GPIOD->PUPDR==0x2468ACE0U && GPIOD->ODR==0x1234);
 /* A1 buffered PA9 and A3 buffered PA12 modes/pulls are not latch outputs. */
 CHECK((GPIOA->MODER&((3U<<18)|(3U<<24)))==(0xA5555555U&((3U<<18)|(3U<<24))));
 CHECK((GPIOA->PUPDR&~(3U<<4))==(0x5AAAAAAAU&~(3U<<4)));
}
int main(void){
 unsigned cases=0;
 #define CASE(setup,error) do{init();setup;execute(USB_SHUTDOWN_REQUIRED,error);cases++;}while(0)
 CASE((void)0,USB_SHUTDOWN_OK);
 for(unsigned bit=0;bit<4;bit++){init();execute(USB_SHUTDOWN_REQUIRED&~(1U<<bit),USB_SHUTDOWN_BAD_PREREQUISITES);cases++;}
 init();execute(31,USB_SHUTDOWN_BAD_PREREQUISITES);cases++;
 CASE(mock_ipsr=3,USB_SHUTDOWN_BAD_CONTEXT);
 CASE(mock_faultmask=1,USB_SHUTDOWN_BAD_CONTEXT);
 CASE(mock_control=1,USB_SHUTDOWN_BAD_CONTEXT);
 CASE(SCB->CCR=SCB_CCR_IC_Msk,USB_SHUTDOWN_BAD_CONTEXT);
 CASE(SCB->CCR=SCB_CCR_DC_Msk,USB_SHUTDOWN_BAD_CONTEXT);
 CASE(FPU->FPCCR=FPU_FPCCR_LSPACT_Msk,USB_SHUTDOWN_BAD_CONTEXT);
 CASE(fault=1,USB_SHUTDOWN_BAD_CLOCKS);CASE(fault=2,USB_SHUTDOWN_BAD_CLOCKS);
 CASE(fault=3,USB_SHUTDOWN_HOLD_UNAVAILABLE);
 CASE(RCC->AHB5ENR|=RCC_AHB5ENR_SDMMC2EN,USB_SHUTDOWN_STORAGE_ACTIVE);
 CASE(RCC->AHB5ENR|=RCC_AHB5ENR_XSPI2EN,USB_SHUTDOWN_OTHER_CLIENT_ACTIVE);
 CASE(RCC->AHB5ENR|=RCC_AHB5ENR_OTG2EN,USB_SHUTDOWN_OTHER_CLIENT_ACTIVE);
 CASE(RCC->APB5ENR=RCC_APB5ENR_CSIEN,USB_SHUTDOWN_OTHER_CLIENT_ACTIVE);
 CASE(RCC->APB1ENR1=RCC_APB1ENR1_I2C2EN,USB_SHUTDOWN_OTHER_CLIENT_ACTIVE);
 CASE(fault=4,USB_SHUTDOWN_PIN_READBACK);
 CASE(fault=5,USB_SHUTDOWN_PERIPHERAL_READBACK);
 CASE(RCC->MISCENR=0,USB_SHUTDOWN_DEBUG_UNAVAILABLE);
 CASE(fault=6,USB_SHUTDOWN_DEBUG_EMULATION);
 CASE(BSEC->SFSRx[3]=0,USB_SHUTDOWN_OTP_UNKNOWN);
 CASE(BSEC->OTPVLDRx[3]=0,USB_SHUTDOWN_OTP_UNKNOWN);
 CASE(BSEC->FVRw[124]=1U<<11,USB_SHUTDOWN_RESET_OPTION);
 CASE(BSEC->FVRw[124]=1,USB_SHUTDOWN_HARDWARE_WATCHDOG);
 CASE(fault=7,USB_SHUTDOWN_PENDING_SOURCE);CASE(fault=8,USB_SHUTDOWN_PENDING_SOURCE);
 CASE(fault=9,USB_SHUTDOWN_MODE_READBACK);CASE(fault=10,USB_SHUTDOWN_PENDING_SOURCE);
 CASE(fault=11,USB_SHUTDOWN_MODE_READBACK);
 CASE(wfi_return=1,USB_SHUTDOWN_UNEXPECTED_RETURN);
 printf("{\"cases\":%u,\"checks\":%u,\"hardware_access\":false,\"standby_entry_proven\":false}\n",cases,asserts);
 return 0;
}
'''


class ShutdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (TC / 'arm-none-eabi-gcc.exe').exists():
            raise unittest.SkipTest('ARM toolchain not installed')
        OUT.mkdir(parents=True, exist_ok=True)
        cls.cc = TC / 'arm-none-eabi-gcc.exe'

    def test_native_register_model_guards(self):
        compiler = shutil.which('clang') or shutil.which('gcc')
        self.assertTrue(compiler, 'Native compiler required for register-model tests')
        macros = run([self.cc, *FLAGS, '-dM', '-E', HERE / 'shutdown.c'])
        header, definitions, clears = make_platform(macros)
        (OUT / 'shutdown_test_platform.h').write_text(header)
        (OUT / 'shutdown_test.c').write_text(HARNESS.replace('DEFINITIONS', definitions).replace('CLEARS', clears))
        exe = OUT / 'shutdown_test.exe'
        run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
             '-DUSB_SHUTDOWN_HOST_TEST', '-I' + str(HERE), '-I' + str(OUT),
             HERE / 'shutdown.c', OUT / 'shutdown_test.c', '-o', exe])
        result = run([exe])
        (OUT / 'native-results.json').write_text(result)
        evidence = json.loads(result)
        self.assertGreaterEqual(evidence['cases'], 34)
        self.assertGreater(evidence['checks'], 300)
        self.assertFalse(evidence['hardware_access'])
        self.assertFalse(evidence['standby_entry_proven'])

    def test_real_arm_release_bytes_and_no_external_calls(self):
        elf, binary = OUT / 'shutdown.elf', OUT / 'shutdown.bin'
        (OUT / 'shutdown.ld').write_text('ENTRY(usb_shutdown_enter)\nSECTIONS { . = 0x34300000; .text : { *(.text*) *(.rodata*) } .data : { *(.data*) } .bss (NOLOAD) : { *(.bss*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) } }\n')
        run([self.cc, *FLAGS, '-nostdlib', HERE / 'shutdown.c',
             '-T' + str(OUT / 'shutdown.ld'), '-Wl,--build-id=none', '-o', elf])
        run([TC / 'arm-none-eabi-objcopy.exe', '-O', 'binary', elf, binary])
        symbols = run([TC / 'arm-none-eabi-nm.exe', '-n', elf])
        listing = run([TC / 'arm-none-eabi-objdump.exe', '-d', elf])
        (OUT / 'shutdown.lst').write_text(listing)
        (OUT / 'shutdown.symbols').write_text(symbols)
        self.assertNotRegex(symbols, r'(?m)^\s+U ')
        labels = {name: int(addr, 16) for addr, name in re.findall(r'^([0-9a-f]+) [A-Za-z] (\S+)$', symbols, re.M)}
        begin, end = labels['usb_shutdown_hold_release'], labels['usb_shutdown_hold_end']
        blob = binary.read_bytes()
        group = blob[begin - 0x34300000:end - 0x34300000]
        self.assertEqual(group, STANDBY_OPCODES)
        self.assertEqual(labels['usb_shutdown_wfi'], begin + 40)
        self.assertEqual(labels['usb_shutdown_hold_reassert'], begin + 42)
        (OUT / 'arm-results.json').write_text(json.dumps(dict(
            bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest(),
            hold_bytes=len(group), hold_sha256=hashlib.sha256(group).hexdigest(),
            symbols=labels, hardware_access=False, standby_entry_proven=False), indent=2) + '\n')

    def test_production_has_no_dependency_on_test_hooks_or_live_cleanup(self):
        source = (HERE / 'shutdown.c').read_text()
        self.assertNotRegex(source, r'\b(?:HAL_|sd_|photo_|ptp_|NVIC_SystemReset)\w*\s*\(')
        self.assertNotRegex(source, r'\b(?:XSPI1|SDMMC2|USB1_OTG_HS|CSI|DCMIPP|I2C2)->')
        self.assertNotRegex(source, r'(?:BSEC|RTC|TAMP)->[^;]*=(?!=)')
        self.assertEqual(source.count('"wfi\\n"'), 0)  # sole WFI is within the pinned assembly group
        self.assertEqual(source.count('usb_shutdown_wfi:\\nwfi\\n'), 1)
        self.assertNotRegex(source, r'trial_entry_proven\s*=\s*1')


if __name__ == '__main__':
    unittest.main(verbosity=2)
