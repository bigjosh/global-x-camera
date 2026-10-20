"""Offline execution of save_main control flow with mocked hardware/FS/encoder.

Production C is copied unchanged except physical memory addresses are rebound
to host arrays. CMSIS cache calls are modeled events, not cache-coherency proof.
The actual ARM binary must still be built/reviewed and qualified on hardware.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent

CMSIS=r"""
#pragma once
#include <stdint.h>
typedef struct { uint32_t CCR; } FakeScb;
typedef struct { uint32_t CTRL, CYCCNT; } FakeDwt;
typedef struct { uint32_t CTRL; } FakeMpu;
extern FakeScb fake_scb;
extern FakeDwt fake_dwt;
extern FakeMpu fake_mpu;
extern uint32_t fake_report[128], fake_trace[64], fake_raw[10], fake_stack[16384];
extern uint8_t fake_frame[3055360+32], fake_request[64], fake_card[512], fake_fs[512];
#define SCB (&fake_scb)
#define DWT (&fake_dwt)
#define MPU (&fake_mpu)
#define SCB_CCR_DC_Msk 0x10000U
#define SCB_CCR_IC_Msk 0x20000U
#define MPU_CTRL_ENABLE_Msk 1U
#define DWT_CTRL_CYCCNTENA_Msk 1U
void mock_barrier(void), mock_enable_dc(void), mock_disable_dc(void);
void mock_disable_ic(void);
#define __DSB() mock_barrier()
#define __ISB() ((void)0)
#define __get_MSPLIM() 0x343A0000U
#define SCB_EnableDCache() mock_enable_dc()
#define SCB_DisableDCache() mock_disable_dc()
#define SCB_DisableICache() mock_disable_ic()
#define SCB_InvalidateICache() ((void)0)
#define SCB_EnableICache() (SCB->CCR |= SCB_CCR_IC_Msk)
"""

HARNESS=r"""
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include "save_under_test.c"
FakeScb fake_scb;
FakeDwt fake_dwt;
FakeMpu fake_mpu;
uint32_t fake_report[128], fake_trace[64], fake_raw[10], fake_stack[16384];
uint8_t fake_frame[3055360+32], fake_request[64], fake_card[512], fake_fs[512];
static int scenario, enables, disables, init_calls, deinit_calls, terminal_barriers;
static photo_fs_report_t fs_result;
void mock_barrier(void) {
    DWT->CYCCNT+=10;
    if(fake_report[P_TERMINAL]==0x444F4E45U) {
        terminal_barriers++;
        /* An invalid incoming cache is not owned/changed by this module. */
        assert(scenario==7 || !(SCB->CCR&0x30000U));
        assert(fake_report[P_STATE]!=1);
        if(enables) assert(disables==1);
    }
}
void mock_enable_dc(void) {
    assert(!fake_report[P_TERMINAL] && fake_report[P_NONCE]==177);
    assert(fake_report[P_MAGIC]==SAVE_REPORT_MAGIC);
    assert(!(SCB->CCR&SCB_CCR_DC_Msk) && !(MPU->CTRL&1));
    enables++; SCB->CCR|=SCB_CCR_DC_Msk;
}
void mock_disable_dc(void) {
    assert(!fake_report[P_TERMINAL] && enables==1);
    disables++; SCB->CCR&=~SCB_CCR_DC_Msk;
    /* Model a discrepancy visible only after dirty cache is cleaned/disabled. */
    if(scenario==10) fake_frame[0]^=1;
}
void mock_disable_ic(void) {
    assert(!fake_report[P_TERMINAL]);
    SCB->CCR&=~SCB_CCR_IC_Msk;
}
void status_led_set(unsigned state) { (void)state; }
const photo_fs_report_t *photo_fs_get_report(void) { return &fs_result; }
int sd_init(sd_card_t *c,uint32_t hz) {
    init_calls++; c->clock_hz=hz; c->initialized=c->controller_owned=1;
    if(scenario==1) { c->error=15; c->media_idle=0; return 15; }
    c->media_idle=1; return 0;
}
int sd_deinit(sd_card_t *c) {
    deinit_calls++;
    if(scenario==5) { c->media_idle=0; c->error=12; return 12; }
    c->initialized=c->controller_owned=0; return 0;
}
int photo_fs_mount(sd_card_t *c) {
    (void)c; if(scenario==2) { fs_result.fat_result=3; return -1; } return 0;
}
int photo_fs_format(sd_card_t *c) { (void)c; return 0; }
int photo_fs_open(uint32_t size) { (void)size; return scenario==16 ? -1 : 0; }
int photo_fs_append(const void *data,size_t bytes) {
    (void)data; fs_result.bytes_written+=(uint32_t)bytes;
    return scenario==17 ? -1 : 0;
}
int photo_fs_finish(void) {
    if(scenario==4) return -1;
    fs_result.completed=1; memcpy(fs_result.final_name,"IMG00001.PNG",13); return 0;
}
int photo_fs_readback(const char *name,uint32_t offset,void *buf,
                      uint32_t length,uint32_t *got) {
    (void)name; (void)offset;
    assert(buf==scratch.read && length==262144);
    memset(buf,0x5A,length); *got=length; return 0;
}
png16_result png16_encode(const uint8_t *p,size_t size,uint32_t w,uint32_t h,
                         size_t stride,png16_mode mode,void *work,size_t worksize,
                         png16_write_fn write,void *user,png16_stats *stats) {
    (void)p;(void)size;(void)w;(void)h;(void)stride;(void)mode;
    assert(work==scratch.png.bytes && worksize==PNG16_WORKSPACE_BYTES);
    if(scenario==3) return PNG16_COMPRESS_FAILED;
    uint8_t bytes[4]={1,2,3,4};
    if(!write(user,bytes,sizeof(bytes))) return PNG16_WRITE_FAILED;
    stats->output_bytes=4; stats->rows_encoded=1364; stats->callback_calls=1;
    return PNG16_OK;
}
int main(int argc,char **argv) {
    assert(argc==2); scenario=atoi(argv[1]);
    fake_scb.CCR=0x201; fake_dwt.CTRL=1; fake_mpu.CTRL=4;
    for(unsigned i=0;i<16384;i++) fake_stack[i]=0x5354414B;
    fake_trace[0]=0x43545031; fake_trace[1]=40; fake_trace[5]=1;
    fake_trace[12]=SAVE_FRAME_ADDRESS; fake_trace[13]=SAVE_FRAME_BYTES;
    fake_trace[14]=SAVE_WIDTH; fake_trace[15]=SAVE_HEIGHT;
    fake_trace[11]=frame_fnv();
    fake_raw[0]=0x52313046; fake_raw[1]=SAVE_FRAME_BYTES;
    fake_raw[8]=10; fake_raw[9]=0x2B;
    uint32_t *g=(void *)(fake_frame+SAVE_FRAME_BYTES);
    for(unsigned i=0;i<8;i++) g[i]=0xA15A1000+i;
    unsigned op=scenario==8 || scenario==11 ? SAVE_OP_READ :
                scenario==15 ? SAVE_OP_FORMAT : SAVE_OP_SAVE;
    save_request_t *r=(void *)fake_request;
    r->magic=SAVE_REQUEST_MAGIC; r->operation=op; r->mode=1;
    r->sd_clock_hz=25000000; r->nonce=177;
    memcpy(r->name,"IMG00001.PNG",13); r->length=scenario==11 ? 262145 : 262144;
    if(scenario==6) fake_mpu.CTRL=5;
    if(scenario==7) fake_scb.CCR|=SCB_CCR_DC_Msk;
    if(scenario==9) fake_trace[11]^=1;
    if(scenario==12) r->magic=0;
    if(scenario==13) fake_trace[0]=0;
    if(scenario==14) fake_dwt.CTRL=0;
    int result=save_main(0x80000000U|op,1);
    int before_enable=scenario==7 || scenario==12 || scenario==13 ||
                      scenario==14 || (SAVE_DATA_CACHE && scenario==6);
    assert(enables==(SAVE_DATA_CACHE && !before_enable));
    assert(disables==enables);
    assert(fake_report[P_TERMINAL]==0x444F4E45 && terminal_barriers==1);
    assert(fake_report[P_CACHE_ENABLED]==(unsigned)enables);
    assert(fake_report[P_RESULT]==(uint32_t)result);
    int should_pass=scenario==0 || scenario==8 || scenario==15 ||
                    (!SAVE_DATA_CACHE && (scenario==6 || scenario==10));
    assert((result==0)==should_pass);
    assert(fake_report[P_STATE]==(should_pass ? 2U : 3U));
    if(before_enable) assert(!init_calls && !deinit_calls);
    if(scenario==1) assert(!fake_report[P_MEDIA_IDLE] && !deinit_calls);
    if(scenario==5) assert(!fake_report[P_MEDIA_IDLE] && deinit_calls==1);
    if(scenario==8) {
        assert(fake_report[P_BUFFER_BYTES]==262144 && fake_report[P_READ_BYTES]==262144);
        assert(scratch.read[0]==0x5A && scratch.read[262143]==0x5A);
    } else assert(fake_report[P_BUFFER_BYTES]==(op==SAVE_OP_READ ? 262144U : 32768U));
    if(scenario==0 || scenario==10) {
        assert(fake_report[P_POSTCLEAN_VALIDATED]==1);
        assert((fake_report[P_POSTCLEAN_FNV]==fake_report[P_FNV_BEFORE])==
               (scenario==0 || !SAVE_DATA_CACHE));
    }
    if(scenario==9) assert(!fake_report[P_POSTCLEAN_VALIDATED]);
    puts("ok"); return 0;
}
"""


class SaveCacheControlFlow(unittest.TestCase):
    def test_actual_control_flow_both_variants(self):
        compiler=shutil.which("clang")
        self.assertIsNotNone(compiler,"native clang is required")
        with tempfile.TemporaryDirectory(prefix="capture-sd-cache-test-") as temp:
            out=Path(temp)
            (out/"stm32n6xx.h").write_text(CMSIS)
            (out/"status_leds.h").write_text(
                "#define STATUS_LED_NAND_WRITE 1\n#define STATUS_LED_ERROR 2\n"
                "#define STATUS_LED_OFF 0\nvoid status_led_set(unsigned);\n")
            for src in (HERE/"photo_fs.h",HERE.parent/"sd-storage/sd_card.h",
                        HERE.parent/"png-encoder/png16.h"):
                shutil.copyfile(src,out/src.name)
            protocol=(HERE/"save_protocol.h").read_text()
            for literal,array in (("0x343F9F00U","fake_request"),("0x343FA000U","fake_report"),
                                  ("0x343FA200U","fake_card"),("0x343FA400U","fake_fs")):
                protocol=protocol.replace(literal,f"((uintptr_t){array})")
            (out/"save_protocol.h").write_text(protocol)
            source=(HERE/"save_main.c").read_text()
            for old,new in (
                ("(const uint8_t *)SAVE_FRAME_ADDRESS","fake_frame"),
                ("(const void *)SAVE_FRAME_ADDRESS","fake_frame"),
                ("(void *)(SAVE_FRAME_ADDRESS+SAVE_FRAME_BYTES)","(void *)(fake_frame+SAVE_FRAME_BYTES)"),
                ("(void *)0x343F0000U","(void *)fake_trace"),
                ("(volatile uint32_t *)0x343F0000U","(volatile uint32_t *)fake_trace"),
                ("(void *)0x343F6000U","(void *)fake_raw"),
                ("(volatile uint32_t *)0x343A0000U","(volatile uint32_t *)fake_stack"),
                ("(void *)0x343A0000U","(void *)fake_stack")):
                self.assertIn(old,source)
                source=source.replace(old,new)
            (out/"save_under_test.c").write_text(source)
            (out/"test.c").write_text(HARNESS)
            for cache in (0,1):
                exe=out/f"test-{cache}.exe"
                subprocess.run([compiler,"-std=c11","-O1","-Wall","-Wextra","-Werror",
                                "-Wno-pointer-to-int-cast",f"-DSAVE_DATA_CACHE={cache}",
                                "-I",str(out),str(out/"test.c"),"-o",str(exe)],check=True)
                for scenario in range(18):
                    with self.subTest(cache=cache,scenario=scenario):
                        subprocess.run([str(exe),str(scenario)],check=True,
                                       capture_output=True,text=True,timeout=10)


if __name__=="__main__":
    unittest.main()
