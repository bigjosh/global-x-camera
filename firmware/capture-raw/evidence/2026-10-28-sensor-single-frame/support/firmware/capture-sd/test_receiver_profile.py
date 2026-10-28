"""Actual-C receiver completion tests for normal/diagnostic proof semantics."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from receiver_profile import POST_FRAME, transform, profile_metadata, check_regions, check_early_regions

HERE = Path(__file__).resolve().parent
FROZEN = HERE / "evidence/2026-10-20-hardware/build/receiver/capture.c"

HARNESS = r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <setjmp.h>
#include "capture_profile.h"
#define WIDTH 4U
#define HEIGHT 2U
#define BYTES (WIDTH*HEIGHT*2U)
#define FAST_SHUTDOWN_DATA_OFF 1
#define DCMIPP_PIPE0 0U
#define DCMIPP_VIRTUAL_CHANNEL0 0U
static uint32_t proof[32],trace[64],fast[32],raw[10],guards[8],early_sensor[32];
static uint8_t g_frame[BYTES];
static unsigned frames=1,vsyncs=1,errors,scenario,reads,stop_order,failed;
static struct { uint32_t SR0,SR1,VC0CFGR1; } csi;
static struct { uint32_t P0DCCNTR,P0PPCR,P0DCLMTR,P0FSCR,CMSR2; } cam;
static struct { uint32_t ErrorCode; } hcam;
static int sensor;
static uint32_t tick=1000;
static jmp_buf finish;
#define CPROF proof
#define TRACE trace
#define FAST fast
#define CSI (&csi)
#define DCMIPP (&cam)
#define __DMB() ((void)0)
#define __DSB() ((void)0)
static uint32_t cycles(void) { return tick+=100; }
static void event(unsigned id) { (void)id; }
static void fast_snapshot(unsigned id) { (void)id; }
static void fail(unsigned where,int result) { assert(result);failed=where;longjmp(finish,1); }
static void check(unsigned where,int result) { if(result) fail(where,result); }
static int rd16(void *p,unsigned reg,uint16_t *v) {
 (void)p;reads++;*v=reg==0x0300?(scenario==2?100:1236):42;return scenario==8?-1:0;
}
static int rd8(void *p,unsigned reg,uint8_t *v) {
 (void)p;reads++;*v=reg==0x030A?(scenario==3?8:10):reg==0x030F?0x2B:0;return 0;
}
static int rd32(void *p,unsigned reg,uint32_t *v) { (void)p;(void)reg;reads++;*v=42;return 0; }
static int HAL_DCMIPP_CSI_PIPE_Stop(void *p,unsigned a,unsigned b) {
 (void)p;(void)a;(void)b;assert(stop_order++==0);return scenario==4?-1:0;
}
static void fast_shutdown_data_off(void) { assert(stop_order++==1);if(scenario==5) fail(0xA5,-1); }
static int VD6G_Stop(void *p) { (void)p;assert(stop_order++==2);return scenario==6?-1:0; }
static void run(void) {
COMPLETION_CODE
}
int main(int argc,char **argv) {
 assert(argc==2);scenario=atoi(argv[1]);cam.P0DCCNTR=BYTES;
 for(unsigned i=0;i<8;++i) guards[i]=0xA15A1000U+i;
 for(unsigned i=0;i<BYTES;++i) g_frame[i]=(uint8_t)(i*13);
 for(unsigned i=0;i<32;++i) proof[i]=0xA5A5A5A5U;
 trace[8]=trace[9]=trace[10]=trace[11]=0xFFFFFFFFU;
 if(scenario==1) guards[3]^=1;
 if(scenario==7) errors=1;
 if(scenario==9) cam.P0DCCNTR--;
 if(scenario==10) frames=2;
 if(scenario==11) hcam.ErrorCode=1;
 if(!setjmp(finish)) run();
 if(scenario) { assert(failed && proof[CP_STATE]==1);return 0; }
 assert(!failed && proof[CP_STATE]==2 && proof[CP_SCHEMA]==2 && proof[CP_WORDS]==32);
 assert(proof[CP_PROFILE]==CAPTURE_DIAGNOSTICS && proof[CP_FLAGS]==(CAPTURE_DIAGNOSTICS?0x7FU:0x1FU));
 assert(proof[CP_BYTES]==BYTES && proof[CP_DMA_BYTES]==BYTES && proof[CP_CANARY_MASK]==255);
 assert(proof[CP_BITS]==10 && proof[CP_DATA_TYPE]==0x2B && proof[CP_ERRORS]==0);
 assert(stop_order==3 && reads==(CAPTURE_DIAGNOSTICS?13:3));
 assert(proof[CP_POST_FRAME_BEGIN]<proof[CP_ESSENTIAL_DONE]);
 assert(proof[CP_PIPE_STOP_BEGIN]<proof[CP_PIPE_STOP_DONE]);
 assert(proof[CP_PIPE_STOP_DONE]<proof[CP_DATA_OFF_DONE]);
 assert(proof[CP_DATA_OFF_DONE]<proof[CP_SENSOR_STOP_DONE]);
 assert(proof[CP_SENSOR_STOP_DONE]<proof[CP_HANDOFF_READY]);
 if(CAPTURE_DIAGNOSTICS) {
  uint32_t expected=2166136261U;
  for(unsigned i=0;i<BYTES;++i) expected=(expected^g_frame[i])*16777619U;
  assert(proof[CP_FNV]==expected && trace[11]==expected);
  assert(proof[CP_SCAN_BEGIN]<proof[CP_SCAN_DONE] && proof[CP_DIAGNOSTIC_READS_BEGIN]<proof[CP_DIAGNOSTIC_READS_DONE]);
 } else {
  assert(!trace[8] && !trace[9] && !trace[10] && !trace[11] && !proof[CP_FNV]);
  assert(!proof[CP_SCAN_BEGIN] && !proof[CP_SCAN_DONE] && !proof[CP_DIAGNOSTIC_READS_BEGIN] && !proof[CP_DIAGNOSTIC_READS_DONE]);
 }
 for(unsigned i=27;i<32;++i) assert(!proof[i]);
 return 0;
}
'''


class ReceiverProfileTests(unittest.TestCase):
    def test_actual_completion_checks_and_skipped_proofs(self):
        compiler = shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(compiler)
        body = POST_FRAME.replace("(volatile uint32_t *)0x343F6000U", "raw")
        body = body.replace("(volatile uint32_t *)(0x34000000U+BYTES)", "guards")
        body = body.replace("DWT->CYCCNT", "cycles()")
        with tempfile.TemporaryDirectory(prefix="receiver-profile-") as temp:
            folder = Path(temp)
            source = folder / "test.c"
            source.write_text(HARNESS.replace("COMPLETION_CODE", body), encoding="utf-8")
            for profile in (0, 1):
                executable = folder / f"test-{profile}.exe"
                subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra",
                                "-Wno-pointer-to-int-cast", "-Wno-unused-function",
                                f"-DCAPTURE_DIAGNOSTICS={profile}", f"-I{HERE}",
                                str(source), "-o", str(executable)], check=True)
                for scenario in range(12):
                    with self.subTest(profile=profile, scenario=scenario):
                        subprocess.run([str(executable), str(scenario)], check=True)

    def test_proof_regions_and_profile_metadata(self):
        regions = check_regions()
        self.assertEqual(regions["FAST"]["end_exclusive"], "0x343f8880")
        self.assertEqual(regions["LED"]["start"], "0x343f89c0")
        self.assertEqual(regions["LED"]["end_exclusive"], "0x343f8a40")
        self.assertEqual(regions["RCP2"]["start"], "0x343f8a80")
        self.assertEqual(regions["RCP2"]["end_exclusive"], "0x343f8b00")
        self.assertEqual(len(regions), 22)
        early = check_early_regions()
        self.assertEqual(len(early), 12)
        self.assertEqual(early["PREFIX_STACK_RESERVED"],
                         {"start": "0x34182000", "end_exclusive": "0x34188000"})
        with self.assertRaises(AssertionError):
            check_regions(overrides={"RCP2": (0x343F8A00, 128)})
        with self.assertRaises(AssertionError):
            check_regions(overrides={"RCP2": (0x343F9E00, 128)})
        # Read the real header, rather than merely comparing two hardcoded
        # addresses. A future LED proof expansion must fail before compilation.
        with tempfile.TemporaryDirectory(prefix="receiver-region-") as temp:
            header = Path(temp) / "status_leds.h"
            actual = (HERE.parent / "capture-timing/status_leds/status_leds.h").read_text(encoding="utf-8")
            header.write_text(actual.replace("#define STATUS_LED_PROOF_WORDS 32U",
                                             "#define STATUS_LED_PROOF_WORDS 64U"), encoding="utf-8")
            with self.assertRaises(AssertionError): check_regions(status_led_header=header)
        self.assertEqual(profile_metadata("normal")["required_performed_flags"], "0x1f")
        self.assertEqual(profile_metadata("diagnostic")["required_performed_flags"], "0x7f")
        with self.assertRaises(ValueError): profile_metadata("unknown")

    def test_frozen_transform_preserves_guard_paths(self):
        source = FROZEN.read_text(encoding="utf-8")
        # The archived v50 completion body is the v45b body; remove only its
        # later storage handoff to reconstruct the transform's frozen input.
        start = source.index("  extern int photo_save_load(void);")
        source = source[:start] + "  event(40);\n  status_led_complete_sleep();\n}\n"
        transformed = transform(source)
        for name, end in (("static void fast_snapshot", "/* Dedicated current-run ForceRx proof"),
                          ("static void ready_force_guard", "static void ready_force_stop_seen"),
                          ("static void fast_shutdown_data_off", "#endif"),
                          ("static void error_event", "void HAL_DCMIPP_PIPE_ErrorCallback")):
            self.assertEqual(source[source.index(name):source.index(end, source.index(name))],
                             transformed[transformed.index(name):transformed.index(end, transformed.index(name))])
        with self.assertRaises(ValueError): transform(transformed)


if __name__ == "__main__":
    unittest.main()
