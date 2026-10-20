"""Offline tests: actual bridge C guards, READ-only host policy, PNG decoding."""
import importlib.util
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

import run as r

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("peripheral_tests",HERE.parent/"test_peripherals.py")
defs=importlib.util.module_from_spec(spec); spec.loader.exec_module(defs)

FAKE=r"""
#pragma once
#include <stdint.h>
typedef struct { uint32_t CFGR1,CFGR2,PLL1CFGR1,PLL1CFGR2,PLL1CFGR3;
 uint32_t IC1CFGR,IC2CFGR,DIVENR,AHB5ENR,AHB5RSTR,AHB4ENR,MEMENR; } Rcc;
typedef struct { uint32_t CCR; } Scb;
typedef struct { uint32_t FPCCR; } Fpu;
typedef struct { uint32_t CTRL; } Mpu;
typedef struct { uint32_t CTRL,CYCCNT; } Dwt;
typedef struct { uint32_t DEMCR; } Debug;
typedef struct { uint32_t MODER; } Gpio;
typedef struct { uint32_t SR; } Xspi;
extern Rcc rcc; extern Scb scb; extern Fpu fpu; extern Mpu mpu;
extern Dwt dwt; extern Debug debug; extern Gpio gpio; extern Xspi xspi;
extern uint32_t request[4],proof[23],memory[32],context[5],scenario;
Xspi *checked_xspi(void);
Gpio *checked_gpio(void);
#define RCC (&rcc)
#define SCB (&scb)
#define FPU (&fpu)
#define MPU (&mpu)
#define DWT (&dwt)
#define CoreDebug (&debug)
#define GPIOG checked_gpio()
#define XSPI1 checked_xspi()
#define SCB_CCR_IC_Msk 0x20000U
#define SCB_CCR_DC_Msk 0x10000U
#define CoreDebug_DEMCR_TRCENA_Msk 0x1000000U
#define DWT_CTRL_CYCCNTENA_Msk 1U
#define __get_CONTROL() context[0]
#define __get_IPSR() context[1]
#define __get_PRIMASK() context[2]
#define __get_FAULTMASK() context[3]
#define __DSB() do {} while(0)
#define __NOP() do { if(scenario!=23) dwt.CYCCNT++; } while(0)
"""
HARNESS=r"""
#include <assert.h>
#include <stdlib.h>
#include "under_test.c"
Rcc rcc; Scb scb; Fpu fpu; Mpu mpu; Dwt dwt; Debug debug; Gpio gpio; Xspi xspi;
uint32_t request[4],proof[23],memory[32],context[5],scenario;
unsigned initialized=0;
Xspi *checked_xspi(void) {
 assert((rcc.AHB5ENR&0x2020)==0x2020 && !(rcc.AHB5RSTR&0x2020));
 return &xspi;
}
Gpio *checked_gpio(void) { assert(rcc.AHB4ENR&RCC_AHB4ENR_GPIOGEN); return &gpio; }
void raw10_memory_init(void) {
 initialized++; memory[0]=0x5231304d; memory[1]=scenario==22;
 rcc.MEMENR=0x55;
}
int main(int argc,char **argv) {
 assert(argc==2); scenario=(uint32_t)atoi(argv[1]);
 request[0]=0x52425231;request[1]=123;context[2]=1;
 rcc.CFGR1=0x33330000;rcc.CFGR2=0x00100000;
 rcc.PLL1CFGR1=0x00404b00;rcc.PLL1CFGR3=0x49000005;
 rcc.IC1CFGR=0x20000;rcc.IC2CFGR=0x30000;rcc.DIVENR=RCC_DIVENR_IC2EN;
 rcc.AHB5ENR=0x2020;rcc.AHB4ENR=RCC_AHB4ENR_GPIOGEN;gpio.MODER=0x00110001;
 switch(scenario) {
 case 1:request[0]=0;break;case 2:request[1]=0;break;case 3:request[2]=1;break;
 case 4:scb.CCR=0x20000;break;case 5:scb.CCR=0x10000;break;
 case 6:context[0]=12;break;case 7:context[1]=3;break;
 case 8:context[2]=0;break;case 9:context[3]=1;break;
 case 10:fpu.FPCCR=1;break;case 11:mpu.CTRL=1;break;
 case 12:rcc.CFGR2=0;break;case 13:rcc.PLL1CFGR3=0;break;
 case 14:rcc.DIVENR=0;break;case 15:rcc.AHB5ENR&=~0x20U;break;
 case 16:rcc.AHB5RSTR=0x20;break;case 17:rcc.AHB5ENR|=RCC_AHB5ENR_SDMMC2EN;break;
 case 18:xspi.SR=XSPI_SR_BUSY;break;case 19:xspi.SR=XSPI_SR_FLEVEL;break;
 case 20:rcc.AHB4ENR=0;break;case 21:gpio.MODER=0;break;
 case 24:mpu.CTRL=4;break;
 }
 int rc=readback_boot_main();
 assert(proof[P_TERMINAL]==0x5242444e && proof[P_NONCE]==request[1]);
 if(scenario==0 || scenario==24) {
  assert(rc==0 && proof[P_STAGE]==3 && initialized==1 && proof[P_DWT_DELTA]==32);
 } else {
  assert(rc!=0);
  assert(initialized==(scenario==22 || scenario==23));
 }
 assert(rcc.CFGR1==0x33330000); /* No CPU/PLL clock changes. */
 return 0;
}
"""


class Tests(unittest.TestCase):
    def test_actual_boot_c_guards(self):
        compiler=shutil.which("clang") or shutil.which("gcc")
        self.assertTrue(compiler)
        source=(HERE/"boot.c").read_text()
        for name,value in (("REQUEST","request"),("PROOF","proof"),("MEMORY","memory")):
            source=re.sub(rf"^#define {name} .+$",f"#define {name} {value}",
                          source,flags=re.M)
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)
            (work/"stm32n657xx.h").write_text(FAKE+"\n"+defs.required_defines(source+HARNESS))
            (work/"under_test.c").write_text(source)
            (work/"main.c").write_text(HARNESS)
            exe=work/"test.exe"
            subprocess.run([compiler,"-std=c11","-O2","-Wall","-Wextra","-Werror",
                            "-I",str(work),str(work/"main.c"),"-o",str(exe)],check=True)
            for scenario in range(25):
                with self.subTest(scenario=scenario):
                    subprocess.run([str(exe),str(scenario)],check=True,capture_output=True)

    def test_read_requests_cannot_select_mutating_operation(self):
        raw,req=r.read_request("IMG00042.PNG",262144,12)
        self.assertEqual((req["operation"],req["mode"],req["length"]),(3,1,262144))
        self.assertEqual(struct.unpack_from("<3I",raw),(0x53525131,3,1))
        for name,offset,nonce in (("../image",0,1),("IMG00042.TMP",0,1),
                ("IMG00042.PNG",1,1),("IMG00042.PNG",3145728,1),("IMG00042.PNG",0,0)):
            with self.subTest(name=name,offset=offset,nonce=nonce):
                with self.assertRaises(ValueError): r.read_request(name,offset,nonce)
        for names in ([],["IMG00001.PNG"]*2,["IMG00001.PNG"]*17):
            with self.assertRaises(ValueError): r.checked_names(names)

    def test_stale_or_failed_boot_rejected(self):
        words=[0x52425231,1,23,14,0,3,0x201,0,0,1,0,0,4,0x33330000,
               0x00100000,0x2020,0,0,0,0x55,1,32,0x5242444e]
        self.assertEqual(r.checked_boot(struct.pack("<23I",*words),14)["stage"],3)
        for index,value in ((3,13),(4,7),(5,2),(6,0x20201),(11,1),(12,5),(17,0x20),
                            (20,0),(21,0),(22,0)):
            altered=words.copy();altered[index]=value
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    r.checked_boot(struct.pack("<23I",*altered),14)

    def test_read_write_diagnostics_rejected(self):
        m=dict(buffer_address="0x34326b40",buffer_bytes=32768,
               read_buffer_address="0x3432eb40",read_buffer_bytes=262144,
               cache_report_extension=1,data_cache_enabled=True)
        report=dict(magic=0x53564431,schema=1,words=128,state=2,result=0,
            terminal=0x444f4e45,cpu_hz=400000000,media_idle=1,card_error=0,
            fs_result=0,width=1120,height=1364,frame_bytes=3055360,
            buffer_bytes=262144,buffer_address=0x3432eb40,stack_canary=0x5354414b,
            initial_msplim=0x343a0000,operation=3,mode=1,nonce=1,stack_used=1024,
            ccr=0x201,read_bytes=100,cache_enabled=1,final_ccr=0x201,complete=200,
            total=100,initial_mpu_ctrl=4,png_bytes=0,fnv_before=0,fnv_after=0,
            postclean_validated=0)
        card=dict(error=0,media_idle=1,initialized=0,controller_owned=0,
                  written_sectors=0,write_cycles=0)
        fs=dict(fat_result=0,bytes_written=0,completed=0)
        _,request=r.read_request("IMG00001.PNG",0,1)
        r.read_only_success(report,card,fs,m,request)
        for target,key,value in ((report,"nonce",2),(report,"operation",2),
                (report,"postclean_validated",1),(card,"written_sectors",1),
                (card,"write_cycles",1),(card,"media_idle",0),(fs,"bytes_written",1)):
            original=target[key];target[key]=value
            with self.subTest(key=key):
                with self.assertRaises(ValueError): r.read_only_success(report,card,fs,m,request)
            target[key]=original

    def test_complete_png_decode_crc_and_hash(self):
        def png_chunk(kind,data):
            return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
        rows=(b"\0"+struct.pack(">H",64)*1120)*1364
        raw=(b"\x89PNG\r\n\x1a\n"+
             png_chunk(b"IHDR",struct.pack(">IIBBBBB",1120,1364,16,0,0,0,0))+
             png_chunk(b"sBIT",b"\x0a")+png_chunk(b"IDAT",zlib.compress(rows))+
             png_chunk(b"IEND",b""))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"IMG00001.PNG";path.write_bytes(raw)
            result=r.verify_png(path,r.sd.sha(raw))
            self.assertEqual(result["pixels"],1120*1364)
            self.assertFalse(result["exact_capture_pixel_comparison"])
            self.assertFalse(result["discernible_dynamic_range"])
            with self.assertRaises(ValueError): r.verify_png(path,"0"*64)
            for altered in (raw[:-1],raw+b"x",raw[:40]+bytes([raw[40]^1])+raw[41:]):
                path.write_bytes(altered)
                with self.assertRaises(ValueError): r.verify_png(path)


if __name__=="__main__":
    unittest.main()
