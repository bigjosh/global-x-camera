"""Offline tests: actual bridge C guards, READ-only host policy, PNG decoding."""
import importlib.util
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest import mock
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
    def test_exact_recovery_pair_and_byte_changes(self):
        legacy=r.ROOT/"firmware/capture-sd/evidence/2026-10-20-low-power/build/prefix"
        identity=r.checked_recovery(legacy)
        self.assertEqual(identity,dict(name="v59",prefix_sha256=r.RECOVERY_SHA,
                                      sector_sha256=r.SECTOR_SHA))
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)
            prefix=(legacy/"stage1.bin").read_bytes()
            sector=(legacy/"capture_sector_0.bin").read_bytes()
            for bad_prefix,bad_sector in (
                    (prefix[:-1],sector),(prefix,sector[:-1]),
                    (bytes([prefix[0]^1])+prefix[1:],sector),
                    (prefix,sector[:-1]+bytes([sector[-1]^1]))):
                (work/"stage1.bin").write_bytes(bad_prefix)
                (work/"capture_sector_0.bin").write_bytes(bad_sector)
                with self.assertRaises(ValueError): r.checked_recovery(work)

    def test_fresh_recovery_result_must_match_selected_image(self):
        identity=dict(prefix_sha256=r.RECOVERY_SHA,sector_sha256=r.SECTOR_SHA,name="v59")
        r.checked_recovery_result(dict(passed=True,prefix_sha256=r.RECOVERY_SHA),identity)
        for result in ({},dict(passed=False,prefix_sha256=r.RECOVERY_SHA),
                       dict(passed=1,prefix_sha256=r.RECOVERY_SHA),
                       dict(passed=True,prefix_sha256="0"*64)):
            with self.assertRaises(ValueError): r.checked_recovery_result(result,identity)

    def test_withdrawn_v63_overlap_candidate_is_rejected(self):
        prefix="d7732adf26fbd058cecd628d2ccf44e0b4e08cadb977ed51d0ff626f08dc6708"
        sector="8226ba5c4aa9ac6ad2b04a358f38cf19fc7902dc9b39abaffbad75ac7923b192"
        self.assertNotIn(prefix,r.APPROVED_RECOVERY)
        # Early recovery was unchanged, but its later RCP2 proof overlapped
        # LED1. The uninstalled candidate must not remain an approved pair.
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)
            (work/"stage1.bin").write_bytes(bytes(5140))
            (work/"capture_sector_0.bin").write_bytes(bytes(65536))
            for digests in ([prefix,sector],[prefix,r.SECTOR_SHA],
                            [r.RECOVERY_SHA,sector],["0"*64]):
                with mock.patch.object(r.sd,"sha",side_effect=digests):
                    with self.assertRaises(ValueError): r.checked_recovery(work)

    def test_v65_pair_selection_never_accepts_mixed_or_arbitrary_hashes(self):
        prefix="6f07ee096565b43a8d5c1f09a0dc28e300599667bda4b025868cb278288baefb"
        sector="409628f664b41b39b8a6397d9098a7bd3420d23c9d8441538e11e59ae9ee593c"
        self.assertEqual(r.APPROVED_RECOVERY[prefix],
            dict(name="v65-normal-standby",sector_sha256=sector))
        # Exact candidate bytes are independently reviewed; this unit test
        # isolates pair selection from the separately tested SHA function.
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)
            (work/"stage1.bin").write_bytes(bytes(5140))
            (work/"capture_sector_0.bin").write_bytes(bytes(65536))
            with mock.patch.object(r.sd,"sha",side_effect=[prefix,sector]):
                identity=r.checked_recovery(work)
            r.checked_recovery_result(dict(passed=True,prefix_sha256=prefix),identity)
            with self.assertRaises(ValueError):
                r.checked_recovery_result(dict(passed=True,prefix_sha256=r.RECOVERY_SHA),identity)
            for digests in ([prefix,r.SECTOR_SHA],[r.RECOVERY_SHA,sector],["0"*64]):
                with mock.patch.object(r.sd,"sha",side_effect=digests):
                    with self.assertRaises(ValueError): r.checked_recovery(work)

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

    def test_v66c_exact_selection_and_cross_pair_rejection(self):
        prefix="247f27c231e0053b7024af29914c6a0cb1b7decb1632ac0d6142a68b89e2da58"
        sector="8129f9cc79e92c678207b4aee838810cc805d0b860c40b2f77b434ae746c8b61"
        self.assertEqual(r.APPROVED_RECOVERY[prefix],
            dict(name="v66c-normal-standby",sector_sha256=sector))
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)
            (work/"stage1.bin").write_bytes(bytes(5140))
            (work/"capture_sector_0.bin").write_bytes(bytes(65536))
            with mock.patch.object(r.sd,"sha",side_effect=[prefix,sector]):
                identity=r.checked_recovery(work)
            r.checked_recovery_result(dict(passed=True,prefix_sha256=prefix),identity)
            for other_prefix,other in r.APPROVED_RECOVERY.items():
                if other_prefix==prefix: continue
                with mock.patch.object(r.sd,"sha",side_effect=[prefix,other['sector_sha256']]):
                    with self.assertRaises(ValueError): r.checked_recovery(work)
                with mock.patch.object(r.sd,"sha",side_effect=[other_prefix,sector]):
                    with self.assertRaises(ValueError): r.checked_recovery(work)
                with self.assertRaises(ValueError):
                    r.checked_recovery_result(dict(passed=True,prefix_sha256=other_prefix),identity)

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

    def test_v15_exact_pair_in_both_recovery_gates(self):
        prefix="db234498a9b347f6cb9f41daf22da1fb0f9266dba264b9ca203ef33d1b1711df"
        sector="efb3c440e008e448a1682285034fe30b77bdbb5834024da9de787f3f51f42629"
        old_prefix="82ce8c0411a0990c7a5081633cb358012bbd081fcb7368241010091f7d1f913b"
        old_sector="03cbd89553944838922bbcd7e2b21813297f3466db64730c5e3e2903a7942424"
        spec=importlib.util.spec_from_file_location("v15_check_park",
            r.ROOT/"firmware/capture-timing/recovery_gpio/check_park.py")
        park=importlib.util.module_from_spec(spec); spec.loader.exec_module(park)
        self.assertEqual(r.APPROVED_RECOVERY[prefix],
                         dict(name="raw-v15-standby",sector_sha256=sector))
        self.assertEqual(park.APPROVED[prefix],
                         dict(bytes=5140,park=0x3418078C,vcp=True,sector=sector))
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)
            (work/"stage1.bin").write_bytes(bytes(5140))
            (work/"capture_sector_0.bin").write_bytes(bytes(65536))
            with mock.patch.object(r.sd,"sha",side_effect=[prefix,sector]):
                identity=r.checked_recovery(work)
            r.checked_recovery_result(dict(passed=True,prefix_sha256=prefix),identity)
            for pair in ([prefix,old_sector],[old_prefix,sector],["0"*64]):
                with mock.patch.object(r.sd,"sha",side_effect=pair):
                    with self.assertRaises(ValueError): r.checked_recovery(work)
            with self.assertRaises(ValueError):
                r.checked_recovery_result(dict(passed=True,prefix_sha256=old_prefix),identity)

    def test_v23_fourbit_125_exact_pair_in_both_gates(self):
        prefix='09fb59cfed0f715927e76f32d5f74187e4c2f1702a70ce192e0d17dcee2f822a'
        sector='bb31867394a4e0d0fb9ab3f9fa96d0d16ffc7256e2a274db74be4f11f9cfdc14'
        old_prefix='9401bed4076d6e9e4d2e4f9236661faf7b8f0e051cb332ea4dcbba09da336eba'
        old_sector='174424c6792f96c72e336fc68e442474e9da665718552d3239a772d59ba73e2e'
        spec=importlib.util.spec_from_file_location('v23_check_park',
            r.ROOT/'firmware/capture-timing/recovery_gpio/check_park.py')
        park=importlib.util.module_from_spec(spec);spec.loader.exec_module(park)
        self.assertEqual(r.APPROVED_RECOVERY[prefix],
            dict(name='raw-v23-fourbit-125-standby',sector_sha256=sector))
        self.assertEqual(park.APPROVED[prefix],
            dict(bytes=5140,park=0x3418078C,vcp=True,sector=sector))
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)
            (work/'stage1.bin').write_bytes(bytes(5140))
            (work/'capture_sector_0.bin').write_bytes(bytes(65536))
            with mock.patch.object(r.sd,'sha',side_effect=[prefix,sector]):
                identity=r.checked_recovery(work)
            r.checked_recovery_result(dict(passed=True,prefix_sha256=prefix),identity)
            for pair in ([prefix,old_sector],[old_prefix,sector]):
                with mock.patch.object(r.sd,'sha',side_effect=pair):
                    with self.assertRaises(ValueError):r.checked_recovery(work)
            with self.assertRaises(ValueError):
                r.checked_recovery_result(dict(passed=True,prefix_sha256=old_prefix),identity)

    def test_phase25_qualification_pairs_and_cross_pair_rejection(self):
        candidates=(
            ('0752c9f4186ccada85f8d242163316d730dd1d22522c831f6382da9f125ed4b7',
             '109a71a99cf69e9061dfe6867003da3316df93e38021bc84c5d03ea401a2a95a',
             'raw-25-negedge-speed3-awake-qualification'),
            ('6858d267f89814ba87326dde34e3c763b0fb6a2c5c82ab437ea3bf19a0eaf5b7',
             '79c7c4ef3fb7d06baf3c2fb16dccaae4cd7f585c2319af7065f939bd006a39cd',
             'raw-25-negedge-speed3-standby-qualification'))
        spec=importlib.util.spec_from_file_location('phase25_check_park',
            r.ROOT/'firmware/capture-timing/recovery_gpio/check_park.py')
        park=importlib.util.module_from_spec(spec);spec.loader.exec_module(park)
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)
            (work/'stage1.bin').write_bytes(bytes(5140))
            (work/'capture_sector_0.bin').write_bytes(bytes(65536))
            for prefix,sector,name in candidates:
                with self.subTest(name=name):
                    self.assertEqual(r.APPROVED_RECOVERY[prefix],
                        dict(name=name,sector_sha256=sector))
                    self.assertEqual(park.APPROVED[prefix],
                        dict(bytes=5140,park=0x3418078C,vcp=True,sector=sector))
                    with mock.patch.object(r.sd,'sha',side_effect=[prefix,sector]):
                        identity=r.checked_recovery(work)
                    r.checked_recovery_result(dict(passed=True,prefix_sha256=prefix),identity)
                    for other_prefix,other in r.APPROVED_RECOVERY.items():
                        if other_prefix==prefix:continue
                        for pair in ([prefix,other['sector_sha256']],[other_prefix,sector]):
                            with mock.patch.object(r.sd,'sha',side_effect=pair):
                                with self.assertRaises(ValueError):r.checked_recovery(work)
                        with self.assertRaises(ValueError):
                            r.checked_recovery_result(
                                dict(passed=True,prefix_sha256=other_prefix),identity)

    def test_phase125_reviewed50_and_startup_pairs_and_cross_pair_rejection(self):
        candidates=(
            ('571660be49caafcfc167e295514c4c1863b8fe35c06192a3cdd184647e39ba38',
             '39cdee32788c08ae81d8b3e35de6ec846d50044433f6aad6633a645585ff2bc7',
             'raw-25-reviewed-startup-awake-qualification'),
            ('0592a543cb1e75b176e97f715f139a0a13d8a4d791ba44efd0ec94dc4f5b6754',
             'c68593cebeddf5b9c24f85249505ae719dd1ea73d11f309e3a8553e9c1a9fa47',
             'raw-25-reviewed-startup-standby-qualification'),
            ('2ff3c9b33dda25456724811d1bf7ccaeac0f6912336f92bcc41b7ee72c304d22',
             'c85907d0c29da1bfa6905734b65f7af3a73a73db70d1f2186065405a5aeb467f',
             'raw-125-negedge-init-speed3-awake-qualification'),
            ('d5f17279640f5acd9642a28fa0df11bddf1825a2b9d06432908ef4a460204c60',
             '4762bbe49e5d48bba5869892f327b8871fccaf8f543cde550ab7858252949945',
             'raw-125-negedge-init-speed3-standby-qualification'),
            ('005230cf308432650a0967d68e2c292c77aaa5aae6a7cab0f8b2d8c865529dee',
             '1faea44570f9284fa239a50db8bb5d1856d7c15645828df6869070bca9b135eb',
             'raw-50-reviewed-awake-unqualified'),
            ('1c5e443b23ea34a6474fbf35d2c43964684b7e4315500d5bd6b4a3143ffbe95d',
             'cc8a35dba9d7c9692424e3f904e3ef8fd8a2b6fc4713730e71767653ea37bed5',
             'raw-50-reviewed-standby-unqualified'),
            ('54cd99f5b2c02c6561e25d8a59fc98210ecdd799736a0a3a8c749cac57a63777',
             'c6a9779db35a458fb2415754c480cc1274d01f662e62fb57a245882cc5db532a',
             'raw-125-reviewed-startup-awake-qualification'),
            ('4ef99d3b0b8ac7b790265cd1994428a5804dd3a20ad5587dd1585d2544a74b0b',
             'c03e40c8ceea09bd9c171c179f2191a1ef9799c9e615db979a84b9c53ad66010',
             'raw-125-reviewed-startup-standby-qualification'))
        spec=importlib.util.spec_from_file_location('phase125_check_park',
            r.ROOT/'firmware/capture-timing/recovery_gpio/check_park.py')
        park=importlib.util.module_from_spec(spec);spec.loader.exec_module(park)
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)
            (work/'stage1.bin').write_bytes(bytes(5140))
            (work/'capture_sector_0.bin').write_bytes(bytes(65536))
            for prefix,sector,name in candidates:
                with self.subTest(name=name):
                    self.assertEqual(r.APPROVED_RECOVERY[prefix],
                        dict(name=name,sector_sha256=sector))
                    self.assertEqual(park.APPROVED[prefix],
                        dict(bytes=5140,park=0x3418078C,vcp=True,sector=sector))
                    with mock.patch.object(r.sd,'sha',side_effect=[prefix,sector]):
                        identity=r.checked_recovery(work)
                    r.checked_recovery_result(dict(passed=True,prefix_sha256=prefix),identity)
                    with mock.patch.object(r.sd,'sha',side_effect=['0'*64]):
                        with self.assertRaises(ValueError):r.checked_recovery(work)
                    for other_prefix,other in r.APPROVED_RECOVERY.items():
                        if other_prefix==prefix:continue
                        for pair in ([prefix,other['sector_sha256']],[other_prefix,sector]):
                            with mock.patch.object(r.sd,'sha',side_effect=pair):
                                with self.assertRaises(ValueError):r.checked_recovery(work)
                        with self.assertRaises(ValueError):
                            r.checked_recovery_result(
                                dict(passed=True,prefix_sha256=other_prefix),identity)

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
