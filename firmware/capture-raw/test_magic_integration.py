"""Execute generated capture validation and magic publication with modeled I/O.

No instruments, debugger, card, or disk device are accessed. The host process
maps ordinary anonymous RAM at MCU SRAM addresses to run the actual generated
functions. This verifies software boundaries, not camera DMA visibility or the
electrical safety of a clock-stalled SD transfer.
"""
import importlib.util
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def function(source, signature):
    """Extract an actual simple C function, preserving its complete body."""
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 1
    at = opening + 1
    while depth:
        depth += (source[at] == "{") - (source[at] == "}")
        at += 1
    return source[start:at]


class MagicIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(HERE))
        try:
            cls.builder = load_module("magic_capture_builder_test", HERE / "build.py")
            cls.transform = load_module("magic_transform_test", HERE / "magic_transform.py")
            cls.source = cls.transform.transform(cls.builder.transform_capture(
                (cls.builder.BASE / "receiver/capture.c").read_text()))
        finally:
            sys.path.remove(str(HERE))

    def test_actual_generated_validation_and_publication(self):
        compiler = shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(compiler, "host C compiler required")
        shutdown = function(self.source, "static int fast_shutdown_data_off(void)")
        poll = function(self.source, "void raw_capture_poll(void)")
        macros = self.source[self.source.index("#define MAGIC_FAIL"):self.source.index("void raw_capture_poll(void)")]
        publisher = function((HERE / "magic_runtime.inc").read_text(), "static int magic_publish(")
        init_begin = self.source.index("  volatile uint32_t *guard=(volatile uint32_t *)(RAW_FRAME_ADDRESS+BYTES);")
        init_end = self.source.index("  __DSB();", init_begin)
        seed = "static void seed_guards(void) {\n" + self.source[init_begin:init_end] + "}\n"
        # Undefined fail/check symbols deliberately make a missed returning
        # conversion fail compilation; the original functions park forever.
        program = HARNESS + seed + shutdown + "\n" + macros + poll + "\n" + publisher + CASES
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "magic-integration.c"
            executable = Path(temp) / "magic-integration.exe"
            source.write_text(program)
            for exposure in (1428, 63000):
                subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                "-Wno-pointer-to-int-cast", "-I" + str(HERE),
                                "-I" + str(ROOT / "firmware/raw-slots"),
                                "-I" + str(ROOT / "firmware/capture-sd"),
                                f"-DRAW_EXPOSURE_COARSE={exposure}U",
                                str(source), str(HERE / "producer.c"), "-o", str(executable)], check=True)
                subprocess.run([str(executable)], check=True, timeout=10)

    def test_generated_allocation_geometry_in_arm_elf(self):
        # Link the actual generated allocation declaration with ARM relocation
        # rules. This catches alignment/offset/size regressions hidden by host
        # pointer size or manually constructed test buffers.
        declaration = next(line for line in self.source.splitlines()
                           if "uint8_t raw_frame_allocation[" in line)
        alias = next(line for line in self.source.splitlines() if line.startswith("#define g_frame "))
        addresses = "\n".join(line for line in (HERE / "runtime.h").read_text().splitlines()
                              if line.startswith(("#define RAW_FRAME_ADDRESS 0x340000A0",
                                                  "#define RAW_SLOT_BUFFER_ADDRESS ")))
        program = '#include "magic_slots.h"\n' + addresses + "\n" + declaration + "\n" + alias + r'''
const uint32_t layout[] = {
    (uint32_t)raw_frame_allocation, (uint32_t)g_frame,
    sizeof(raw_frame_allocation), RAW_FRAME_ADDRESS, RAW_SLOT_BUFFER_ADDRESS,
    RAW_FRAME_ADDRESS+MAGIC_SLOTS_IMAGE_BYTES,
    RAW_SLOT_BUFFER_ADDRESS+MAGIC_SLOTS_PADDED_BYTES,
    MAGIC_SLOTS_PADDING_BYTES, MAGIC_SLOTS_IMAGE_OFFSET,
    MAGIC_SLOTS_METADATA_BYTES
};
'''
        linker = "SECTIONS { . = 0x34000000; .frame (NOLOAD) : { *(.psram_bss) } " \
                 ". = 0x34300000; .rodata : { *(.rodata*) } }"
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "layout.c").write_text(program)
            (directory / "layout.ld").write_text(linker)
            executable = directory / "layout.elf"
            subprocess.run([str(self.builder.TC / "arm-none-eabi-gcc.exe"),
                            "-mcpu=cortex-m55", "-mthumb", "-nostdlib", "-Wall", "-Wextra", "-Werror",
                            "-I" + str(ROOT / "firmware/raw-slots"),
                            "-T" + str(directory / "layout.ld"), str(directory / "layout.c"),
                            "-o", str(executable)], check=True)
            data = directory / "layout.bin"
            subprocess.run([str(self.builder.TC / "arm-none-eabi-objcopy.exe"),
                            "-O", "binary", "--only-section=.rodata", str(executable), str(data)], check=True)
            base, frame, size, expected_frame, slot, original, tail, padding, image_offset, metadata = struct.unpack("<10I", data.read_bytes())
            self.assertEqual((base, frame, expected_frame, slot),
                             (0x34000000, 0x340000A0, 0x340000A0, 0x34000004))
            self.assertEqual(frame % 16, 0)
            self.assertEqual(slot % 4, 0)
            self.assertEqual(original, frame + 1909600)
            self.assertEqual(tail, slot + 3730 * 512)
            self.assertEqual(base + size, tail + 32)
            self.assertEqual((padding, image_offset, metadata), (0, 156, 152))
            self.assertEqual(frame, slot + image_offset)
            self.assertEqual(tail, original + 4)
            self.assertLessEqual(4 + metadata, 512)

    def test_transform_rejects_drift_and_exposure_bounds(self):
        with self.assertRaises(ValueError):
            self.transform.transform("unrecognized capture source")
        base = self.builder.sensor_source((self.builder.BASE / "staged/stage1_sensor.c").read_text())
        for coarse in (1, 1428, 63000):
            sensor = self.transform.sensor_exposure(base, coarse)
            manual = re.search(r"manual\[12\]=\{([^}]+)\}", sensor).group(1)
            fields = [int(word, 0) for word in manual.split(",")]
            self.assertEqual(fields[2] | fields[3] << 8, coarse)
            frame_lines = int(re.search(r"write_value\(0x0458,(\d+),2\)", sensor).group(1))
            self.assertGreaterEqual(frame_lines, coarse + 2000)
            self.assertLessEqual(frame_lines, 0xFFFF)
            # The configured 1236-cycle line / 160.8 MHz VT clock keeps even
            # this deliberately long diagnostic integration under 0.5 second.
            self.assertLess(coarse * 1236 / 160800000, 0.5)
        for coarse in (-1, 0, 63001, 65535):
            with self.assertRaises(ValueError):
                self.transform.sensor_exposure(base, coarse)

    def test_flash_refuses_nondefault_exposure_before_building(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "must-not-be-created"
            run = subprocess.run([sys.executable, str(HERE / "build.py"), "--out", str(destination),
                                  "--magic-format", "--line-stream", "--flash",
                                  "--exposure-coarse", "63000"], capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertIn("Nondefault exposure is RAM diagnostic only", run.stderr)
            self.assertFalse(destination.exists())


HARNESS = r'''
#ifndef _WIN32
#define _GNU_SOURCE
#endif
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <sys/mman.h>
#endif
#include "producer.h"
#include "magic_slots.h"
#include "capture_profile.h"
#define RAW_FLASH 0
#define RAW_MAGIC_FORMAT 1
#define RAW_ASYNC_STOP 1
#define RAW_LINE_STREAM 1
#define FAST_SHUTDOWN_DATA_OFF 1
#define WIDTH MAGIC_SLOTS_WIDTH
#define HEIGHT MAGIC_SLOTS_HEIGHT
#define BYTES MAGIC_SLOTS_IMAGE_BYTES
#define RAW_SLOTS_PAYLOAD_BYTES MAGIC_SLOTS_IMAGE_BYTES
#define RAW_FRAME_ADDRESS 0x340000A0U
#define RAW_SLOT_BUFFER_ADDRESS 0x34000004U
#define g_frame ((uint8_t *)RAW_FRAME_ADDRESS)
#define SHUTDOWN ((volatile uint32_t *)0x343F8900U)
#define CPROF ((volatile uint32_t *)CAPTURE_PROFILE_ADDRESS)
#define DCMIPP_PIPE0 0
#define DCMIPP_VIRTUAL_CHANNEL0 0
#define RCC_APB5ENR_CSIEN 1U
#define RCC_APB5ENR_DCMIPPEN 2U
#define RCC_DIVENR_IC18EN 1U
#define RCC_DIVENR_IC17EN 2U
#define RCC_APB5RSTR_CSIRST 1U
#define RCC_APB5RSTR_DCMIPPRST 2U
#define CSI_SR0_VC0STATEF (1U<<17)
#define DCMIPP_P0FCTCR_CPTREQ (1U<<3)
#define DCMIPP_CMSR1_P0CPTACT (1U<<15)
#define DCMIPP_P0FSCR_PIPEN (1U<<31)
#define CSI_PRCR_PEN 1U
#define CSI_PCR_DL0EN 4U
#define CSI_PCR_DL1EN 8U
#define __DSB() ((void)0)
#define __DMB() ((void)0)
#define CLEAR_BIT(reg, bits) do { if(!stuck_clear) (reg)&=~(bits); } while(0)
static struct { uint32_t APB5ENR, DIVENR, APB5RSTR; } mock_rcc;
static struct { uint32_t SR0,SR1,PRCR,PCR,VC0CFGR1; } mock_csi;
static struct { uint32_t P0FCTCR,CMSR1,P0FSCR,P0DCCNTR,P0PPCR,P0DCLMTR,CMSR2; } mock_dcmipp;
static struct { uint32_t CYCCNT; } mock_dwt;
#define RCC (&mock_rcc)
#define CSI (&mock_csi)
#define DCMIPP (&mock_dcmipp)
#define DWT (&mock_dwt)
static struct { uint32_t ErrorCode; } hcam;
static struct { struct { uint32_t is_streaming; } ctx; } sensor;
static uint32_t TRACE[64], FAST[544], raw_magic_proof[8];
static uint32_t frames,vsyncs,errors,capture_async_error,capture_finalizing,capture_ready;
static uint32_t capture_stop_pending,capture_stop_started,capture_stop_poll;
static uint32_t capture_sensor_stopped,capture_exposure_us;
static uint32_t reads,writes,hal_stops,ready_events,stop_events,last_event;
static uint32_t fail_read,line_length,bits,datatype,coarse,ack,state,frame_length,margin;
static int fail_write,stop_error,stuck_clear;
static void event(uint32_t id) { last_event=id; }
static void fast_snapshot(uint32_t id) { (void)id; }
static int rd16(void *p,uint32_t reg,uint16_t *value) {
    (void)p;++reads;if(reg==fail_read)return 1;
    assert(reg==0x0300U || reg==0x0064U || reg==0x0458U || reg==0x0946U);
    *value=(uint16_t)(reg==0x0300U?line_length:reg==0x0064U?coarse:reg==0x0458U?frame_length:margin);return 0;
}
static int rd8(void *p,uint32_t reg,uint8_t *value) {
    (void)p;++reads;if(reg==fail_read)return 1;
    assert(reg==0x030AU || reg==0x030FU || reg==0x0202U || reg==0x0028U);
    *value=(uint8_t)(reg==0x030AU?bits:reg==0x030FU?datatype:reg==0x0202U?ack:state);return 0;
}
static int wr8(void *p,uint32_t reg,uint8_t value) {
    (void)p;assert(reg==0x0202U && value==1U);++writes;return fail_write;
}
static int HAL_DCMIPP_CSI_PIPE_Stop(void *p,uint32_t pipe,uint32_t vc) {
    (void)p;assert(pipe==0U && vc==0U);++hal_stops;return stop_error;
}
static void raw_capture_data_ready(void) { ++ready_events; }
static void raw_capture_stopped(void) { ++stop_events; }
static uint32_t raw_capture_available(void) { return raw_producer_available(&raw_producer); }
static uint32_t raw_capture_frame_validated(void) { return capture_ready; }
static uint32_t raw_capture_sensor_stopped(void) { return capture_sensor_stopped; }
static uint32_t raw_capture_fault(void) { return errors|hcam.ErrorCode|capture_async_error|raw_producer.error; }
'''

CASES = r'''
static volatile uint32_t *original_guard(void) {
    return (volatile uint32_t *)(RAW_FRAME_ADDRESS+BYTES);
}
static volatile uint32_t *end_guard(void) {
    return (volatile uint32_t *)(RAW_SLOT_BUFFER_ADDRESS+MAGIC_SLOTS_PADDED_BYTES);
}
static volatile uint8_t *metadata(void) {
    return (volatile uint8_t *)(RAW_SLOT_BUFFER_ADDRESS+4U);
}
static void assert_metadata_unchanged(void) {
    for(unsigned i=0;i<MAGIC_SLOTS_METADATA_BYTES;i++)
        assert(metadata()[i]==(uint8_t)(i*37U+19U));
}
static void reset_capture(void) {
    memset((void *)0x34000000U,0,4U*1024U*1024U);
    memset(TRACE,0,sizeof(TRACE));memset(FAST,0,sizeof(FAST));
    memset(raw_magic_proof,0,sizeof(raw_magic_proof));
    memset(&mock_rcc,0,sizeof(mock_rcc));memset(&mock_csi,0,sizeof(mock_csi));
    memset(&mock_dcmipp,0,sizeof(mock_dcmipp));
    frames=1;vsyncs=errors=capture_async_error=capture_finalizing=capture_ready=0;
    capture_stop_pending=capture_stop_started=capture_stop_poll=0;
    capture_sensor_stopped=capture_exposure_us=0;hcam.ErrorCode=0;
    reads=writes=hal_stops=ready_events=stop_events=last_event=0;
    fail_read=0xFFFFFFFFU;line_length=1236;bits=10;datatype=0x30;coarse=RAW_EXPOSURE_COARSE;
    frame_length=65000;margin=1000;
    ack=0;state=2;fail_write=stop_error=stuck_clear=0;
    RCC->APB5ENR=3;RCC->DIVENR=3;CSI->PRCR=1;CSI->PCR=15;
    DCMIPP->P0DCCNTR=BYTES;DWT->CYCCNT=1000;
    raw_producer_init(&raw_producer,1);raw_producer_frame(&raw_producer,999);
    /* Startup must actively initialize metadata, including after a warm
     * restart with retained, arbitrary SRAM contents. */
    memset((void *)RAW_SLOT_BUFFER_ADDRESS,0xCD,MAGIC_SLOTS_IMAGE_OFFSET);
    seed_guards();
    assert(*(volatile uint32_t *)RAW_SLOT_BUFFER_ADDRESS==MAGIC_SLOTS_START_MAGIC);
    for(unsigned i=0;i<MAGIC_SLOTS_METADATA_BYTES;i++) {
        assert(metadata()[i]==0);
        metadata()[i]=(uint8_t)(i*37U+19U);
    }
    for(unsigned i=0;i<9;i++) assert(original_guard()[i]==0xA15A1000U+i);
    raw_magic_proof[1]=1U;sensor.ctx.is_streaming=1;
}
static void assert_footer_absent(void) {
    assert(original_guard()[0]!=MAGIC_SLOTS_END_MAGIC);
    assert(raw_magic_proof[1]<2U);
}
int main(void) {
#ifdef _WIN32
    void *memory=VirtualAlloc((void *)0x34000000U,4U*1024U*1024U,
        MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
#else
    void *memory=mmap((void *)0x34000000U,4U*1024U*1024U,
        PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
#endif
    assert(memory==(void *)0x34000000U);
    assert(RAW_SLOT_BUFFER_ADDRESS%4U==0 && RAW_FRAME_ADDRESS%16U==0);
    assert(RAW_FRAME_ADDRESS==RAW_SLOT_BUFFER_ADDRESS+MAGIC_SLOTS_IMAGE_OFFSET);
    assert(MAGIC_SLOTS_IMAGE_OFFSET==156U && MAGIC_SLOTS_METADATA_BYTES==152U);
    assert(MAGIC_SLOTS_TRAILER_OFFSET==156U+BYTES);
    assert(MAGIC_SLOTS_PADDING_BYTES==0 && MAGIC_SLOTS_STRIDE==3730);
    assert(MAGIC_SLOTS_TRAILER_OFFSET+4U==MAGIC_SLOTS_PADDED_BYTES);
    assert((uint8_t *)end_guard()==(uint8_t *)original_guard()+4U);
    reset_capture();frames=0;raw_producer_init(&raw_producer,1);
    uint32_t available=0xFFFFFFFFU;
    assert(!magic_publish(0,&available) && available==0);
    assert(!reads && !hal_stops && !capture_ready);assert_footer_absent();
    for(uint32_t line=1;line<=22;line++) {
        raw_producer_line(&raw_producer,line*1000U,0);
        assert(!magic_publish(0,&available));
        assert(available==(MAGIC_SLOTS_IMAGE_OFFSET+raw_producer.available_bytes)/512U*512U);
        assert(available<=1792000U && !capture_ready && !reads);assert_footer_absent();
        assert_metadata_unchanged();
    }
    /* FRAME validates the image but async sensor STOP has not completed: even
     * full image publication cannot expose the trailing magic sector yet. */
    frames=1;raw_producer_frame(&raw_producer,30000);DWT->CYCCNT=30001;
    assert(!magic_publish(0,&available));
    assert(capture_ready && capture_stop_pending && !capture_sensor_stopped);
    assert(available==3729U*512U && raw_producer.validated);assert_footer_absent();
    assert(capture_exposure_us==(uint64_t)(RAW_EXPOSURE_COARSE*1236ULL*10000ULL+804000ULL)/1608000ULL);
    assert(ready_events==1 && writes==1);
    for(unsigned i=0;i<8;i++) assert(original_guard()[i]==0xA15A1000U+i);
    DWT->CYCCNT+=400000U;
    assert(!magic_publish(0,&available) && available==MAGIC_SLOTS_PADDED_BYTES);
    assert(capture_sensor_stopped && !capture_stop_pending && stop_events==1);
    assert(raw_magic_proof[1]==2 && original_guard()[0]==MAGIC_SLOTS_END_MAGIC);
    assert_metadata_unchanged();
    for(unsigned i=0;i<8;i++) assert(end_guard()[i]==0xA15A1001U+i);
    assert(!magic_publish(0,&available) && available==MAGIC_SLOTS_PADDED_BYTES);
    assert_metadata_unchanged();
    assert(ready_events==1 && writes==1 && hal_stops==1);
    /* Each failure is executed in the returning validator. None may call the
     * original parking helpers, mark ready, or make a completion marker. */
    for(unsigned fault=0;fault<(RAW_EXPOSURE_COARSE==1428U?21U:25U);fault++) {
        reset_capture();
        switch(fault) {
        case 0:DCMIPP->P0DCCNTR--;break;
        case 1:original_guard()[0]^=1;break;
        case 2:fail_read=0x0300;break;
        case 3:line_length--;break;
        case 4:bits=8;break;
        case 5:datatype=0x2B;break;
        case 6:fail_read=0x030A;break;
        case 7:fail_read=0x030F;break;
        case 8:fail_read=0x0064;break;
        case 9:stop_error=1;break;
        case 10:RCC->APB5ENR=0;break;
        case 11:CSI->SR0=CSI_SR0_VC0STATEF;break;
        case 12:CSI->PRCR=0;break;
        case 13:stuck_clear=1;break;
        case 14:fail_write=1;break;
        case 15:frames=2;break;
        case 16:hcam.ErrorCode=1;break;
        case 17:FAST[3]=1;break;
        case 18:raw_producer.frame_seen=0;break;
        case 19:RCC->APB5RSTR=RCC_APB5RSTR_CSIRST;break;
        case 20:coarse--;break;
        case 21:fail_read=0x0458;break;
        case 22:fail_read=0x0946;break;
        case 23:frame_length=margin+6U;break;
        case 24:margin=frame_length-RAW_EXPOSURE_COARSE-6U;break;
        }
        raw_capture_poll();
        assert(raw_capture_fault() && !capture_ready && !ready_events);
        assert(magic_publish(0,&available));assert_footer_absent();
    }
    /* The original/end guards share seven words. Corrupt every distinct word
     * in the combined 36-byte region after validation; all withhold GXRE. */
    for(unsigned which=0;which<9;which++) {
        reset_capture();raw_capture_poll();assert(capture_ready);
        original_guard()[which]^=1;
        DWT->CYCCNT+=400000U;
        assert(magic_publish(0,&available)==2);assert_footer_absent();
    }
    /* Async STOP errors after FRAME return to the SD owner without a footer. */
    for(unsigned fault=0;fault<3;fault++) {
        reset_capture();raw_capture_poll();assert(capture_ready);
        DWT->CYCCNT+=400000U;
        if(fault<2) fail_read=fault==0?0x0202U:0x0028U;
        else DWT->CYCCNT+=400000001U;
        assert(magic_publish(0,&available)==1 && raw_capture_fault());
        assert(!capture_sensor_stopped);assert_footer_absent();
    }
#ifdef _WIN32
    assert(VirtualFree(memory,0,MEM_RELEASE));
#else
    assert(!munmap(memory,4U*1024U*1024U));
#endif
    puts("generated capture, nested failures and magic footer cases passed");
    return 0;
}
'''


if __name__ == "__main__":
    unittest.main()
