"""Exercise actual PHY clock/framing/guard/restore C without hardware.

Only the delay and GPIO-write leaves are modeled; phy_clock_bit is retained.
The PHY advances its output after MDC rising (LAN8742 table5-15). A deliberately
regressed sampling routine must fail the same tests, catching the old one-bit
shift that a framing-only mock missed. This is not electrical qualification.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent

PREFIX = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
typedef struct { uint32_t MODER,OTYPER,OSPEEDR,PUPDR,IDR,ODR,BSRR,AFR[2]; } GPIO_TypeDef;
static GPIO_TypeDef gf,gg;
#define GPIOF (&gf)
#define GPIOG (&gg)
static struct { uint32_t AHB4ENR,AHB4RSTR,AHB4ENSR,AHB4ENCR; } rcc;
#define RCC (&rcc)
static struct { uint32_t CTRL,CYCCNT; } dwt;
#define DWT (&dwt)
static struct { uint32_t DEMCR; } dbg;
#define CoreDebug (&dbg)
#define CoreDebug_DEMCR_TRCENA_Msk 1U
#define DWT_CTRL_CYCCNTENA_Msk 1U
#define RCC_AHB4ENR_GPIOFEN 32U
#define RCC_AHB4ENR_GPIOGEN 64U
#define RCC_AHB4RSTR_GPIOFRST 32U
#define RCC_AHB4RSTR_GPIOGRST 64U
#define RAW_POWER_PROBE 4
#define RAW_FLASH 0
#define RAW_STANDBY 0
static uint32_t __get_IPSR(void) {return 0;}
static uint32_t __get_CONTROL(void) {return 0;}
static uint32_t __get_PRIMASK(void) {return 1;}
static void __disable_irq(void) {}
static void __set_PRIMASK(uint32_t p) {assert(p==1);}
static void __DSB(void) {}
static void __ISB(void) {}
static uint32_t tx[65],pos,regs[32],reads,writes,frames,pullup,host_release,phy_level;
static uint32_t response,badrestore,unstable;
static uint32_t bits(unsigned start,unsigned n) {
 uint32_t v=0;while(n--)v=(v<<1)|tx[start++];return v;
}
static void line(void) {gf.IDR=(host_release&&phy_level&&pullup)?16:0;}
static void mock_put(GPIO_TypeDef *port,uint32_t pin,uint32_t value) {
 if(value)port->ODR|=1U<<pin;else port->ODR&=~(1U<<pin);
 if(((port->MODER>>(2*pin))&3)!=1)return; /* Restored input latch is not a clock. */
 if(port==GPIOF){assert(pin==4);host_release=value;line();return;}
 assert(port==GPIOG&&pin==11);gg.IDR=value?2048:0;
 if(!value)return;
 tx[pos]=host_release;
 if(pos==45) {
  for(unsigned i=0;i<32;i++)assert(tx[i]==1);
  assert(bits(32,2)==1&&bits(36,5)==0&&(bits(34,2)==1||bits(34,2)==2));
  if(bits(34,2)==2){reads++;response=regs[bits(41,5)];
   if(unstable&&bits(41,5)==0&&reads==4)response^=0x100;}
 }
 if(pos==63&&bits(34,2)==1) {
  assert(bits(41,5)==0&&bits(46,2)==2);writes++;
  uint32_t value=bits(48,16);
  if(!(badrestore&&(regs[0]&0x800)&&!(value&0x800)))regs[0]=value;
 }
 /* MDIO output changes after this rising edge, for the NEXT sampling edge. */
 pos++;
 if(bits(34,2)!=2)phy_level=1;
 else if(pos==47)phy_level=0;
 else if(pos>=48&&pos<64)phy_level=(response>>(63-pos))&1;
 else phy_level=1;
 if(pos==65){pos=0;frames++;}
 line();
}
'''

SUFFIX = r'''
#define CHECK(x) do {if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);return 1;}}while(0)
static void setup(void) {
 memset(&gf,0,sizeof(gf));memset(&gg,0,sizeof(gg));memset(&rcc,0,sizeof(rcc));
 gf.MODER=0xA5A5A5A5;gg.MODER=0x5A5A5A5A;gf.ODR=0xA55A;gg.ODR=0x5AA5;
 gf.OTYPER=0xA55A;gg.OTYPER=0x5AA5;gf.OSPEEDR=0x56ABCD12;gg.OSPEEDR=0xABCDEF01;
 gf.PUPDR=0xABCDABCD;gg.PUPDR=0x12341234;gf.AFR[0]=0x12345678;gg.AFR[1]=0x87654321;
 rcc.AHB4ENR=96;dbg.DEMCR=1;dwt.CTRL=1;dwt.CYCCNT=1234;
 memset(tx,0,sizeof(tx));memset(regs,0,sizeof(regs));regs[0]=0x3000;regs[2]=7;regs[3]=0xC131;
 pos=reads=writes=frames=unstable=badrestore=phy_active=0;pullup=host_release=phy_level=1;line();
 memset((void*)raw_power_phy_proof,0,sizeof(raw_power_phy_proof));
}
static int same(GPIO_TypeDef a,GPIO_TypeDef b) {
 return a.MODER==b.MODER&&a.OTYPER==b.OTYPER&&a.OSPEEDR==b.OSPEEDR&&a.PUPDR==b.PUPDR&&
 a.ODR==b.ODR&&a.AFR[0]==b.AFR[0]&&a.AFR[1]==b.AFR[1];
}
int main(int argc,char **argv) {
 if(argc!=2)return 2;
 unsigned test=(unsigned)strtoul(argv[1],0,0);setup();
 if(test==0) {
  const uint32_t patterns[]={0,1,7,0xC131,0x8000,0xAAAA,0x5555,0xFFFF,0x3100};
  for(unsigned i=0;i<sizeof(patterns)/sizeof(patterns[0]);i++) {
   setup();phy_bus bus;CHECK(phy_bus_open(&bus,0)==0);regs[2]=patterns[i];uint32_t v=0;
   CHECK(phy_read(2,&v)==0);CHECK(v==patterns[i]);CHECK(pos==0&&frames==1&&writes==0);
   CHECK(phy_bus_close(&bus,0)==0);
  }
 } else if(test==1) {
  for(unsigned mode=3;mode<=4;mode++) {
   setup();GPIO_TypeDef f=gf,g=gg;
   CHECK(power_phy_begin(mode)==0);CHECK(regs[0]==(mode==4?0x3800:0x3000));
   CHECK(same(f,gf)&&same(g,gg)&&writes==1);
   CHECK(power_phy_restore()==0&&regs[0]==0x3000&&writes==2);
   CHECK(same(f,gf)&&same(g,gg)&&raw_power_phy_proof[E_FLAGS]==3&&raw_power_phy_proof[E_STAGE]==6);
   CHECK(power_phy_restore()==0&&writes==2);
  }
 } else if(test==2) {
  regs[3]=0xffff;CHECK(power_phy_begin(4)==PHY_ID&&writes==0&&!phy_active);
 } else if(test==3) {
  unstable=1;CHECK(power_phy_begin(4)==PHY_BMCR&&writes==0&&!phy_active);
 } else if(test==4) {
  regs[0]|=0x800;CHECK(power_phy_begin(4)==PHY_BMCR&&writes==0);
 } else if(test==5) {
  pullup=0;line();CHECK(power_phy_begin(4)==PHY_PULLUP&&writes==0&&frames==0);
 } else if(test==6) {
  CHECK(power_phy_begin(4)==0);badrestore=1;
  CHECK(power_phy_restore()==PHY_RESTORE_TIMEOUT&&writes==2);
  CHECK(phy_active&&raw_power_phy_proof[E_RESTORE_POLLS]==100&&raw_power_phy_proof[E_FLAGS]==1);
 } else if(test==7) {
  dwt.CTRL=0;CHECK(power_phy_begin(4)==PHY_DWT&&writes==0&&frames==0);
 } else return 3;
 puts("PASS");return 0;
}
'''


def modeled_source(legacy=False):
    source = (HERE / 'power_phy.inc').read_text()
    start = source.index('static int phy_delay')
    end = source.index('static phy_pin phy_snapshot', start)
    source = source[:start] + 'static int phy_delay(uint32_t cycles) {(void)cycles;return 0;}\n' + source[end:]
    start = source.index('static void phy_put')
    end = source.index('static void phy_restore_pin', start)
    source = source[:start] + 'static void phy_put(GPIO_TypeDef *p,uint32_t n,uint32_t v){mock_put(p,n,v);}\n' + source[end:]
    if legacy:
        # Restore only the historical sampling placement, not an unrelated bug.
        sample = '    if(in) *in=(GPIOF->IDR>>4)&1U;\n'
        if source.count(sample) != 1:
            raise ValueError('Sampling statement changed; review the mutation test')
        source = source.replace(sample, '')
        source = source.replace('    e=phy_delay(PHY_HALF);\n    phy_put(GPIOG,11,0);',
                                '    e=phy_delay(PHY_HALF);\n    if(!e && in) *in=(GPIOF->IDR>>4)&1U;\n    phy_put(GPIOG,11,0);', 1)
    return PREFIX + source + SUFFIX


class PowerPhyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('clang') or shutil.which('gcc')
        if not compiler:
            raise RuntimeError('host C compiler required')
        cls.temp = tempfile.TemporaryDirectory()
        cls.outputs = {}
        for name, legacy in [('current', False), ('legacy', True)]:
            source = Path(cls.temp.name) / (name + '.c')
            binary = source.with_suffix('.exe')
            source.write_text(modeled_source(legacy))
            subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                            str(source), '-o', str(binary)], check=True, capture_output=True, text=True)
            cls.outputs[name] = binary

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, case, name='current'):
        return subprocess.run([str(self.outputs[name]), str(case)], capture_output=True, text=True)

    def test_actual_clock_reads_all_bit_patterns(self):
        result = self.run_case(0)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_historical_sample_edge_fails_the_same_read_test(self):
        result = self.run_case(0, 'legacy')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('v==patterns[i]', result.stderr)

    def test_control_and_powerdown_restore_exact_gpio_and_bmcr(self):
        result = self.run_case(1)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mismatch_guards_and_bounded_restore_failure(self):
        for case in range(2, 8):
            with self.subTest(case=case):
                result = self.run_case(case)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
