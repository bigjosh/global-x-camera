"""Execute actual target control flow against modeled registers and encoder.

This is an ordering/guard model, not hardware/cache/timing qualification.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
CMSIS=ROOT/'tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers/CMSIS/Device/ST/STM32N6xx/Include/stm32n657xx.h'
FAKE=r'''
#ifndef MOCK_CMSIS
#define MOCK_CMSIS
#include <stdint.h>
typedef struct {uint32_t CCR;} SCB_Type;
typedef struct {uint32_t CTRL;} MPU_Type;
typedef struct {uint32_t FPCCR;} FPU_Type;
typedef struct {uint32_t CTRL,CYCCNT;} DWT_Type;
typedef struct {uint32_t CFGR1,CFGR2,PLL1CFGR1,PLL1CFGR2,PLL1CFGR3,IC1CFGR,IC2CFGR,DIVENR,AHB5ENR,AHB5RSTR;} RCC_Type;
typedef struct {uint32_t SR;} XSPI_Type;
extern SCB_Type scb; extern MPU_Type mpu; extern FPU_Type fpu; extern RCC_Type rcc;
extern DWT_Type dwt; extern XSPI_Type xspi;
extern uint32_t control,ipsr,primask,faultmask,dc_en,dc_dis,ic_en,ic_dis,xspi_reads;
DWT_Type *tick_dwt(void); XSPI_Type *checked_xspi(void);
#define SCB (&scb)
#define MPU (&mpu)
#define FPU (&fpu)
#define RCC (&rcc)
#define DWT tick_dwt()
#define XSPI1 checked_xspi()
#define __get_CONTROL() control
#define __get_IPSR() ipsr
#define __get_PRIMASK() primask
#define __get_FAULTMASK() faultmask
#define __DSB() ((void)0)
#define __ISB() ((void)0)
#define __NOP() ((void)0)
#define SCB_CCR_IC_Msk (1U<<17)
#define SCB_CCR_DC_Msk (1U<<16)
#define MPU_CTRL_ENABLE_Msk 1U
#define DWT_CTRL_CYCCNTENA_Msk 1U
static inline void SCB_EnableDCache(void){dc_en++;scb.CCR|=SCB_CCR_DC_Msk;}
static inline void SCB_DisableDCache(void){dc_dis++;scb.CCR&=~SCB_CCR_DC_Msk;}
static inline void SCB_InvalidateICache(void){}
static inline void SCB_EnableICache(void){ic_en++;scb.CCR|=SCB_CCR_IC_Msk;}
static inline void SCB_DisableICache(void){ic_dis++;scb.CCR&=~SCB_CCR_IC_Msk;}
{DEFINES}
#endif
'''
HARNESS=r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "stm32n657xx.h"
#include "bench_protocol.h"
#include "png16.h"
SCB_Type scb; MPU_Type mpu; FPU_Type fpu; RCC_Type rcc; DWT_Type dwt; XSPI_Type xspi;
uint32_t control,ipsr,primask,faultmask,dc_en,dc_dis,ic_en,ic_dis,xspi_reads;
pb_report test_report; pb_request test_request; pb_chunk test_chunks[PB_MAX_CHUNKS];
uint8_t test_frame[PB_FRAME_BYTES]; uint32_t test_frame_guard[8],test_stack_guard;
static unsigned encoder_calls,encoder_fail;
DWT_Type *tick_dwt(void){dwt.CYCCNT+=100;return &dwt;}
XSPI_Type *checked_xspi(void){assert((rcc.AHB5ENR&0x2020)==0x2020);assert(!(rcc.AHB5RSTR&0x2020));xspi_reads++;return &xspi;}
void png_bench_prepare_main(void); void png_bench_run_main(void);
png16_result png16_encode_timed(const uint8_t *input,size_t bytes,uint32_t width,uint32_t height,
 size_t stride,png16_mode mode,void *workspace,size_t wn,png16_write_fn write,void *user,
 png16_stats *stats,const png16_timing_config *t)
{
 (void)input;(void)bytes;(void)width;(void)height;(void)stride;(void)mode;(void)workspace;(void)wn;
 const uint8_t data[]={1,2,3,4}; encoder_calls++;
 uint64_t start=t->now(t->user); int ok=write(user,data,4); uint64_t end=t->now(t->user);
 *stats=(png16_stats){4,PB_HEIGHT,1,1};
 t->out->callback_cycles=end-start;
 return encoder_fail || !ok ? PNG16_WRITE_FAILED : PNG16_OK;
}
static uint32_t fnv(const uint8_t *p,size_t n){uint32_t h=2166136261U;while(n--)h=(h^*p++)*16777619U;return h;}
static void setup(void)
{
 scb.CCR=513;mpu.CTRL=4;fpu.FPCCR=0;control=ipsr=faultmask=0;primask=1;
 rcc=(RCC_Type){.CFGR1=0x33330000,.CFGR2=0x00100000,.PLL1CFGR1=0x00404B00,
  .PLL1CFGR3=0x49000005,.IC1CFGR=0x20000,.IC2CFGR=0x30000,.DIVENR=RCC_DIVENR_IC2EN,
  .AHB5ENR=0x2020}; xspi.SR=2; dwt.CTRL=1;dwt.CYCCNT=0;
 dc_en=dc_dis=ic_en=ic_dis=xspi_reads=encoder_calls=encoder_fail=0;
 memset(&test_request,0,sizeof(test_request));test_request.magic=PB_MAGIC;test_request.schema=1;
 test_request.operation=PB_ENCODE;test_request.nonce=123;test_request.mode=1;
 test_request.input_fnv=fnv(test_frame,sizeof(test_frame));
 const uint8_t out[]={1,2,3,4};test_request.output_fnv=fnv(out,4);test_request.output_bytes=4;
 for(unsigned i=0;i<8;i++)test_frame_guard[i]=0x504E4700U+i;
}
int main(void)
{
 for(unsigned scenario=0;scenario<16;scenario++) {
  setup();
  switch(scenario) {
   case 0:test_request.operation=PB_PREPARE;break;
   case 1:break;
   case 2:test_request.magic=0;break;
   case 3:control=12;break;
   case 4:scb.CCR|=SCB_CCR_DC_Msk;break;
   case 5:mpu.CTRL|=1;break;
   case 6:rcc.CFGR1=0;break;
   case 7:rcc.AHB5ENR|=RCC_AHB5ENR_SDMMC2EN;break;
   case 8:rcc.AHB5ENR=0;break;
   case 9:xspi.SR=XSPI_SR_BUSY;break;
   case 10:dwt.CTRL=0;break;
   case 11:test_request.input_fnv^=1;break;
   case 12:test_frame_guard[2]=0;break;
   case 13:encoder_fail=1;break;
   case 14:test_request.output_fnv^=1;break;
   case 15:fpu.FPCCR=1;break;
  }
  if(!scenario)png_bench_prepare_main();else png_bench_run_main();
  assert(test_report.nonce==123);
  assert(test_report.terminal==(!scenario?PB_READY:PB_DONE));
  assert((test_report.result==0)==(scenario<=1));
  if(scenario==1 || scenario==13 || scenario==14) {
   assert(encoder_calls==1 && dc_en==1 && dc_dis==1 && ic_en==1 && ic_dis==1);
   assert(!(scb.CCR&0x30000));assert(test_report.input_fnv_after==test_request.input_fnv);
   assert(test_report.encode_cycles==test_report.sink_cycles+test_report.cpu_cycles);
  } else assert(!encoder_calls && !dc_en && !dc_dis && !ic_en && !ic_dis);
  if(scenario==4)assert(scb.CCR&SCB_CCR_DC_Msk);
  if(scenario==3)assert(control==12);
  if(scenario==8)assert(!xspi_reads);
 }
 puts("16 target guard/cache ownership scenarios passed");return 0;
}
'''

class TargetTests(unittest.TestCase):
    def test_actual_target_control_flow(self):
        header=CMSIS.read_text()
        names=('RCC_IC1CFGR_IC1INT','RCC_IC1CFGR_IC1SEL','RCC_IC2CFGR_IC2INT',
               'RCC_IC2CFGR_IC2SEL','RCC_DIVENR_IC2EN','RCC_AHB5ENR_SDMMC2EN','XSPI_SR_BUSY','XSPI_SR_FLEVEL')
        # Resolve macro dependencies using the real header, leaving no guessed bit masks.
        all_defs=dict(re.findall(r'^#define\s+(\w+)\s+([^\n]+)',header,re.M))
        needed=set(names)
        for _ in range(10):
            prior=set(needed)
            for name in list(needed):needed.update(x for x in re.findall(r'\b[A-Z][A-Za-z0-9_]+\b',all_defs[name]) if x in all_defs)
            if needed==prior:break
        defines='\n'.join('#define '+name+' '+all_defs[name] for name in sorted(needed))
        with tempfile.TemporaryDirectory(prefix='png-target-') as temp:
            out=Path(temp);(out/'stm32n657xx.h').write_text(FAKE.replace('{DEFINES}',defines))
            (out/'test.c').write_text(HARNESS)
            cc=shutil.which('clang') or shutil.which('gcc')
            command=[cc,'-O2','-std=c11','-Wall','-Wextra','-Werror','-DPB_HOST_TEST',
                '-I'+str(out),'-I'+str(HERE),'-I'+str(HERE.parent),str(out/'test.c'),
                str(HERE/'bench_main.c'),str(HERE/'bench_sink.c'),'-o',str(out/'test.exe')]
            built=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stdout+built.stderr)
            ran=subprocess.run([str(out/'test.exe')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            print(ran.stdout.strip())

if __name__=='__main__':unittest.main()
