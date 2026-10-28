"""Compile/run a software-only register and Clause-22 model. No instrument imports.

The production helper's bit-framing/state/cleanup code runs unchanged. Only
three leaf functions (delay, GPIO BSRR, clock bit) are replaced for the host.
This validates framing/guards/restoration, not physical setup/hold or MDIO volts.
"""
from pathlib import Path
import hashlib
import json
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
source=(ROOT/'firmware/capture-raw/power_phy.inc').read_text()
def replace_function(text,start,next_start,body):
    a=text.index(start); b=text.index(next_start,a)
    return text[:a]+body+'\n'+text[b:]
source=replace_function(source,'static int phy_delay','static phy_pin phy_snapshot',
                       'static int phy_delay(uint32_t c) { (void)c; return 0; }')
source=replace_function(source,'static void phy_put','static void phy_restore_pin',
                       'static void phy_put(GPIO_TypeDef *p,uint32_t n,uint32_t v) { if(v) p->ODR|=1U<<n; else p->ODR&=~(1U<<n); if(p==GPIOF && n==4) { if(v && pullup) p->IDR|=1U<<4; else p->IDR&=~(1U<<4); } }')
source=replace_function(source,'static int phy_clock_bit','static int phy_send',
                       'static int phy_clock_bit(uint32_t o,uint32_t *i) { return mock_bit(o,i); }')
prefix=r'''
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
static uint32_t __get_PRIMASK(void) {return 0;}
static void __disable_irq(void) {}
static void __set_PRIMASK(uint32_t p) {(void)p;}
static void __DSB(void) {}
static void __ISB(void) {}
static uint32_t tx[65],pos,phy[32],reads,writes,frames,pullup,unstable,badta,badrestore;
static uint32_t bits(unsigned a,unsigned n) {uint32_t r=0; while(n--)r=(r<<1)|tx[a++]; return r;}
static int mock_bit(uint32_t out,uint32_t *in) {
  tx[pos]=out;
  if(pos==45) {
    for(unsigned n=0;n<32;n++) assert(tx[n]==1);
    assert(bits(32,2)==1 && bits(36,5)==0);
    assert(bits(34,2)==1 || bits(34,2)==2);
    if(bits(34,2)==2) reads++;
  }
  if(pos>=46 && bits(34,2)==2) {
    assert(out==1);
    unsigned r=bits(41,5);
    uint32_t value=phy[r];
    if(unstable && r==0 && reads==4) value^=0x100;
    if(in) *in=pos==47?badta:(pos>=48 && pos<64?((value>>(63-pos))&1):1);
  }
  if(pos==63 && bits(34,2)==1) {
    assert(bits(46,2)==2);
    unsigned r=bits(41,5); uint32_t v=bits(48,16);
    assert(r==0); /* This helper may write BMCR only. */
    if(badrestore && (phy[r]&0x800) && !(v&0x800)) v^=0x100;
    phy[r]=v; writes++;
  }
  pos++;
  if(pos==65) {frames++; pos=0;}
  return 0;
}
'''
suffix=r'''
static void setup(void) {
 memset(&gf,0,sizeof(gf));memset(&gg,0,sizeof(gg));memset(&rcc,0,sizeof(rcc));
 gf.MODER=0xA5A5A5A5;gg.MODER=0x5A5A5A5A;gf.ODR=0xA55A;gg.ODR=0x5AA5;
 gf.OTYPER=0xA55A;gg.OTYPER=0x5AA5;gf.OSPEEDR=0x56ABCD12;gg.OSPEEDR=0xABCDEF01;
 gf.PUPDR=0xABCDABCD;gg.PUPDR=0x12341234;gf.AFR[0]=0x12345678;gg.AFR[1]=0x87654321;
 gf.IDR=16;rcc.AHB4ENR=96;dbg.DEMCR=1;dwt.CTRL=1;dwt.CYCCNT=1234;
 memset(phy,0,sizeof(phy));phy[0]=0x3100;phy[2]=7;phy[3]=0xC134;
 pos=reads=writes=frames=unstable=badta=badrestore=0;pullup=1;phy_active=0;
 memset((void*)raw_power_phy_proof,0,sizeof(raw_power_phy_proof));
}
static void sameconfig(GPIO_TypeDef a,GPIO_TypeDef b) {
 assert(a.MODER==b.MODER && a.OTYPER==b.OTYPER && a.OSPEEDR==b.OSPEEDR &&
 a.PUPDR==b.PUPDR && a.ODR==b.ODR && a.AFR[0]==b.AFR[0] && a.AFR[1]==b.AFR[1]);
}
int main(void) {
 for(unsigned mode=3;mode<=4;mode++) {
  setup();GPIO_TypeDef f=gf,g=gg;
  assert(power_phy_begin(mode)==0);assert(phy[0]==(mode==4?0x3900:0x3100));
  sameconfig(f,gf);sameconfig(g,gg);
  assert(power_phy_restore()==0);assert(phy[0]==0x3100 && writes==2);
  assert(raw_power_phy_proof[E_STAGE]==6 && raw_power_phy_proof[E_FLAGS]==3);
  assert(raw_power_phy_proof[E_RESTORE_CONFIG_MATCH]==1);
  sameconfig(f,gf);sameconfig(g,gg);assert(power_phy_restore()==0 && writes==2);
 }
 setup();phy[3]=0xFFFF;assert(power_phy_begin(4)==PHY_ID);assert(writes==0 && !phy_active);
 setup();unstable=1;assert(power_phy_begin(4)==PHY_BMCR);assert(writes==0 && !phy_active);
 setup();phy[0]|=0x800;assert(power_phy_begin(4)==PHY_BMCR);assert(writes==0);
 setup();pullup=0;assert(power_phy_begin(4)==PHY_PULLUP);assert(writes==0 && frames==0);
 setup();badta=1;assert(power_phy_begin(4)==PHY_TURNAROUND);assert(writes==0);
 setup();badrestore=1;assert(power_phy_begin(4)==0);assert(power_phy_restore()==PHY_RESTORE_TIMEOUT);
 assert(phy_active && raw_power_phy_proof[E_RESTORE_POLLS]==100 && raw_power_phy_proof[E_FLAGS]==1);
 setup();dwt.CTRL=0;assert(power_phy_begin(4)==PHY_DWT);assert(writes==0 && frames==0);
 setup();assert(power_phy_restore()==0 && writes==0 && frames==0);
 puts("PASS: 10 software-only protocol/guard/restore cases");return 0;
}
'''
harness=HERE/'host_model.c'; exe=HERE/'host_model.exe'
harness.write_text(prefix+source+suffix)
command=['clang','-std=c11','-O2','-Wall','-Wextra','-Werror',str(harness),'-o',str(exe)]
subprocess.run(command,check=True)
result=subprocess.check_output([str(exe)],text=True).strip()
record={'source_sha256':hashlib.sha256((ROOT/'firmware/capture-raw/power_phy.inc').read_bytes()).hexdigest(),
        'result':result,'hardware_access':False,'limitations':'Three hardware leaf functions replaced; no physical timing/electrical qualification.',
        'compile_command':command}
(HERE/'offline-model-result.json').write_text(json.dumps(record,indent=2)+'\n')
print(result)
