"""Offline production-PHY tests retain the actual clock/framing/guard code.

Only GPIO writes, RCC set/clear side effects, and elapsed time are modeled.
The PHY advances its next bit immediately after MDC rising; reverting the
sample edge must fail. These tests do not qualify electrical timing or energy.
"""
from pathlib import Path
import re
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
typedef struct {uint32_t MODER,OTYPER,OSPEEDR,PUPDR,IDR,ODR,BSRR,AFR[2];} GPIO_TypeDef;
static GPIO_TypeDef gf,gg;
#define GPIOF (&gf)
#define GPIOG (&gg)
static struct {uint32_t AHB4ENR,AHB4RSTR,AHB4ENSR,AHB4ENCR,
 CFGR1,CFGR2,IC1CFGR,PLL1CFGR1,PLL1CFGR2,PLL1CFGR3;} rcc;
#define RCC (&rcc)
static struct {uint32_t CTRL,CYCCNT;} dwt;
#define DWT (&dwt)
static struct {uint32_t DEMCR;} dbg;
#define CoreDebug (&dbg)
static struct {uint32_t CCR;} scb;
#define SCB (&scb)
#define SCB_CCR_DC_Msk (1U<<16)
#define CoreDebug_DEMCR_TRCENA_Msk 1U
#define DWT_CTRL_CYCCNTENA_Msk 1U
#define RCC_AHB4ENR_GPIOFEN 32U
#define RCC_AHB4ENR_GPIOGEN 64U
#define RCC_AHB4RSTR_GPIOFRST 32U
#define RCC_AHB4RSTR_GPIOGRST 64U
#define RAW_BOARD_ETH_POWERDOWN 1
#define RAW_FLASH 0
static uint32_t ipsr,control,primask,initial_primask,fail_enable,fail_disable,stall;
static uint32_t __get_IPSR(void){return ipsr;}
static uint32_t __get_CONTROL(void){return control;}
static uint32_t __get_PRIMASK(void){return primask;}
static void __disable_irq(void){primask=1;}
static void __set_PRIMASK(uint32_t p){primask=p;}
static void __DSB(void){
 if(!fail_enable)rcc.AHB4ENR|=rcc.AHB4ENSR;
 if(!fail_disable)rcc.AHB4ENR&=~rcc.AHB4ENCR;
 rcc.AHB4ENSR=rcc.AHB4ENCR=0;
}
static void __ISB(void){}
static uint32_t tx[65],pos,regs[32],reads,writes,frames,pullup,host_release,phy_level;
static uint32_t response,unstable,ignore_write,no_ack,no_ack_after_write,put_count;
static uint32_t bits(unsigned start,unsigned n){
 uint32_t v=0;while(n--)v=(v<<1)|tx[start++];return v;
}
static void line(void){gf.IDR=(host_release&&phy_level&&pullup)?16:0;}
static void mock_put(GPIO_TypeDef *port,uint32_t pin,uint32_t value){
 assert((rcc.AHB4ENR&96)==96);assert(!(rcc.AHB4RSTR&96));put_count++;
 if(value)port->ODR|=1U<<pin;else port->ODR&=~(1U<<pin);
 if(((port->MODER>>(2*pin))&3)!=1)return;
 if(port==GPIOF){assert(pin==4);host_release=value;line();return;}
 assert(port==GPIOG&&pin==11);gg.IDR=value?2048:0;
 if(!value)return;
 assert(primask==initial_primask); /* No whole-transaction IRQ mask. */
 tx[pos]=host_release;
 if(pos==45){
  for(unsigned i=0;i<32;i++)assert(tx[i]==1);
  assert(bits(32,2)==1&&bits(36,5)==0&&(bits(34,2)==1||bits(34,2)==2));
  if(bits(34,2)==2){reads++;response=regs[bits(41,5)];
   if(unstable&&bits(41,5)==0&&reads==4)response^=0x100;}
 }
 if(pos==63&&bits(34,2)==1){
  assert(bits(41,5)==0&&bits(46,2)==2);writes++;
  uint32_t value=bits(48,16);assert(value&0x800); /* Never clear PD. */
  if(!ignore_write)regs[0]=value;
 }
 pos++;
 if(bits(34,2)!=2)phy_level=1;
 else if(no_ack||(no_ack_after_write&&writes))phy_level=1;
 else if(pos==47)phy_level=0;
 else if(pos>=48&&pos<64)phy_level=(response>>(63-pos))&1;
 else phy_level=1;
 if(pos==65){pos=0;frames++;}
 line();
}
'''

SUFFIX = r'''
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);return 1;}}while(0)
static void setup(void){
 memset(&gf,0,sizeof(gf));memset(&gg,0,sizeof(gg));memset(&rcc,0,sizeof(rcc));
 gf.MODER=0xA5A5A5A5;gg.MODER=0x5A5A5A5A;gf.ODR=0xA55A;gg.ODR=0x5AA5;
 gf.OTYPER=0xA55A;gg.OTYPER=0x5AA5;gf.OSPEEDR=0x56ABCD12;gg.OSPEEDR=0xABCDEF01;
 gf.PUPDR=0xABCDABCD;gg.PUPDR=0x12341234;gf.AFR[0]=0x12345678;gg.AFR[1]=0x87654321;
 rcc.AHB4ENR=96|0x400;dbg.DEMCR=1;dwt.CTRL=1;dwt.CYCCNT=1234;
 rcc.CFGR1=0x33330000;rcc.CFGR2=0x00100000;rcc.IC1CFGR=0x00020000;
 rcc.PLL1CFGR1=0x00404B00;rcc.PLL1CFGR3=0x49000005;
 scb.CCR=1U<<17; /* Production permits I-cache enabled. */
 memset(tx,0,sizeof(tx));memset(regs,0,sizeof(regs));regs[0]=0x3000;regs[2]=7;regs[3]=0xC131;
 pos=reads=writes=frames=unstable=ignore_write=no_ack=no_ack_after_write=put_count=0;
 ipsr=control=primask=initial_primask=fail_enable=fail_disable=stall=board_eth_attempted=0;
 pullup=host_release=phy_level=1;line();
 memset((void*)raw_board_eth_proof,0,sizeof(raw_board_eth_proof));
}
static int same(GPIO_TypeDef a,GPIO_TypeDef b){
 return a.MODER==b.MODER&&a.OTYPER==b.OTYPER&&a.OSPEEDR==b.OSPEEDR&&a.PUPDR==b.PUPDR&&
 a.ODR==b.ODR&&a.AFR[0]==b.AFR[0]&&a.AFR[1]==b.AFR[1];
}
int main(int argc,char **argv){
 if(argc!=2)return 2;unsigned test=(unsigned)strtoul(argv[1],0,0);setup();
 if(test==0){
  const uint32_t patterns[]={0,1,7,0xC131,0x8000,0xAAAA,0x5555,0xFFFF,0x3100};
  for(unsigned i=0;i<sizeof(patterns)/sizeof(patterns[0]);i++){
   setup();beth_bus bus;CHECK(beth_bus_open(&bus)==0);regs[2]=patterns[i];uint32_t v=0;
   CHECK(beth_read(2,&v)==0);CHECK(v==patterns[i]);CHECK(pos==0&&frames==1&&writes==0);
   CHECK(beth_bus_close(&bus)==0);
  }return 0;
 }
 GPIO_TypeDef f=gf,g=gg;uint32_t expected=0,expected_cleanup=0;
 if(test==1){} /* Qualified new PD. */
 else if(test==2)regs[0]|=0x800; /* Warm-reset PD retention. */
 else if(test==3){regs[3]=0xffff;expected=BETH_ID;}
 else if(test==4){unstable=1;expected=BETH_BMCR;}
 else if(test==5){regs[0]|=0x200;expected=BETH_BMCR;}
 else if(test==6){pullup=0;line();expected=BETH_PULLUP;}
 else if(test==7){no_ack=1;expected=BETH_TURNAROUND;}
 else if(test==8){dwt.CTRL=0;expected=BETH_DWT;}
 else if(test==9){stall=1;expected=BETH_DWT;}
 else if(test==10){rcc.IC1CFGR^=0x10000;expected=BETH_CLOCK;}
 else if(test==11){scb.CCR|=SCB_CCR_DC_Msk;expected=BETH_CONTEXT;}
 else if(test==12){rcc.AHB4ENR&=~96U;} /* Temporarily enable and restore clocks. */
 else if(test==13){rcc.AHB4ENR&=~96U;fail_enable=1;expected=BETH_CLOCK;}
 else if(test==14){ignore_write=1;expected=BETH_VERIFY;}
 else if(test==15){no_ack_after_write=1;expected=BETH_TURNAROUND;}
 else if(test==16){rcc.AHB4ENR&=~96U;fail_disable=1;expected_cleanup=BETH_GPIO_RESTORE;}
 else if(test==17){initial_primask=primask=1;}
 else if(test==18){rcc.AHB4RSTR=32;expected=BETH_CLOCK;}
 else if(test==19){ipsr=1;expected=BETH_CONTEXT;}
 else return 3;
 uint32_t rcc0=rcc.AHB4ENR;
 board_eth_powerdown_once();
 CHECK(raw_board_eth_proof[BE_MAGIC]==0x31485445&&raw_board_eth_proof[BE_VERSION]==1);
 CHECK(raw_board_eth_proof[BE_ERROR]==expected&&raw_board_eth_proof[BE_CLEANUP_ERROR]==expected_cleanup);
 CHECK(raw_board_eth_proof[BE_STAGE]==((expected||expected_cleanup)?0xE1:6));
 CHECK(raw_board_eth_proof[BE_START_TICK]==1234&&raw_board_eth_proof[BE_END_TICK]>=1234);
 CHECK(same(f,gf)&&same(g,gg)&&primask==initial_primask);
 CHECK(raw_board_eth_proof[BE_WRITE_ATTEMPTS]==writes);
 CHECK(raw_board_eth_proof[BE_READ_ATTEMPTS]==reads);
 if(!expected&&!expected_cleanup){
  CHECK(regs[0]==0x3800&&raw_board_eth_proof[BE_REQUESTED]==0x3800);
  if(test==2){
   CHECK(writes==0&&reads==4&&raw_board_eth_proof[BE_FLAGS]==119);
   CHECK(!raw_board_eth_proof[BE_AFTER0]&&!raw_board_eth_proof[BE_AFTER1]);
  }else{
   CHECK(writes==1&&reads==6&&raw_board_eth_proof[BE_FLAGS]==123);
   CHECK(raw_board_eth_proof[BE_AFTER0]==0x3800&&raw_board_eth_proof[BE_AFTER1]==0x3800);
  }
 }else if(test==14||test==15){
  CHECK(writes==1&&(raw_board_eth_proof[BE_FLAGS]&128)&&!(raw_board_eth_proof[BE_FLAGS]&16));
  CHECK(regs[0]==(test==14?0x3000:0x3800));
 }else if(test!=16)CHECK(writes==0);
 if(test==7||test==15)CHECK(pos==0); /* NACK still consumes full frame. */
 if(test==8||test==9||test==10||test==11||test==13||test==18||test==19)
  CHECK(!put_count&&!reads&&!writes); /* Guards before any pad use. */
 if(test!=16)CHECK(rcc.AHB4ENR==rcc0);
 /* Re-entry cannot retry a failed or successful attempt, or erase its proof. */
 uint32_t proof[64];memcpy(proof,(void*)raw_board_eth_proof,sizeof(proof));
 uint32_t old_reads=reads,old_writes=writes,old_put=put_count;
 board_eth_powerdown_once();
 CHECK(reads==old_reads&&writes==old_writes&&put_count==old_put);
 CHECK(!memcmp(proof,(void*)raw_board_eth_proof,sizeof(proof)));
 puts("PASS");return 0;
}
'''


def modeled_source(legacy=False):
    source = (HERE / 'board_eth_powerdown.inc').read_text()
    # Retain the actual bounded delay for the deliberately stalled-DWT case.
    source = source.replace('static int beth_delay(uint32_t cycles)',
                            'static int beth_real_delay(uint32_t cycles)', 1)
    at = source.index('BOARD_ETH_LATE static beth_pin beth_snapshot')
    source = source[:at] + '''static int beth_delay(uint32_t cycles){
 if(stall)return beth_real_delay(cycles);
 dwt.CYCCNT+=cycles;return 0;
}
''' + source[at:]
    start = source.index('BOARD_ETH_LATE static void beth_put')
    end = source.index('BOARD_ETH_LATE static void beth_restore_pin', start)
    source = source[:start] + '''static void beth_put(GPIO_TypeDef *p,uint32_t n,uint32_t v){
 mock_put(p,n,v);
}
''' + source[end:]
    if legacy:
        sample = '    if(in) *in=(GPIOF->IDR>>4)&1U;\n'
        if source.count(sample) != 1:
            raise ValueError('Sampling changed; review the historical mutation')
        source = source.replace(sample, '')
        source = source.replace('    e=beth_delay(BETH_HALF);\n    beth_put(GPIOG,11,0);',
                                '    e=beth_delay(BETH_HALF);\n    if(!e && in) *in=(GPIOF->IDR>>4)&1U;\n    beth_put(GPIOG,11,0);', 1)
    return PREFIX + source + SUFFIX


class BoardEthPowerdownTests(unittest.TestCase):
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
            result = subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                                     str(source), '-o', str(binary)], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stderr)
            cls.outputs[name] = binary

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, case, name='current'):
        return subprocess.run([str(self.outputs[name]), str(case)], capture_output=True, text=True, timeout=5)

    def test_clock_patterns_and_regression_mutation(self):
        result = self.run_case(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_case(0, 'legacy')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('v==patterns[i]', result.stderr)

    def test_new_and_retained_powerdown_restore_owned_resources(self):
        for case in (1, 2, 12, 17):
            with self.subTest(case=case):
                result = self.run_case(case)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_fail_open_warnings_unknown_write_and_bounded_counter(self):
        for case in (3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 18, 19):
            with self.subTest(case=case):
                result = self.run_case(case)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_function_uses_late_section_and_no_constant_tables(self):
        source = (HERE / 'board_eth_powerdown.inc').read_text()
        functions = re.findall(r'^.*\bstatic\s+(?:int|void|beth_pin)\s+\w+\([^;]*?\)\s*\{',
                               source, re.M)
        self.assertGreaterEqual(len(functions), 15)
        self.assertTrue(all(f.startswith('BOARD_ETH_LATE ') for f in functions))
        self.assertIn('section(".raw_late_text"),noinline,noclone', source)
        self.assertNotRegex(source, r'\b(?:static\s+)?const\s+\w+\s+\w+\s*\[')


if __name__ == '__main__':
    unittest.main()
