"""Execute the real optional coordinator wait with a modeled publisher and DWT.

The publication/guard implementation is covered separately by
test_magic_integration.py. These tests exercise its caller's eligibility,
deadline, outcome and fault handling without instruments or device access.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def function(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth, at = 1, opening + 1
    while depth:
        depth += (source[at] == "{") - (source[at] == "}")
        at += 1
    return source[start:at]


class DmaTailWaitTests(unittest.TestCase):
    def test_actual_eligibility_deadline_and_faults(self):
        compiler = shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(compiler, "host C compiler required")
        header = (HERE / "runtime.h").read_text()
        constants = header[header.index("#define RAW_DMA_TAIL_WAIT_MAGIC"):
                           header.index("extern volatile uint32_t raw_dma_tail_wait_proof")]
        body = function((HERE / "magic_runtime.inc").read_text(),
                        "static int magic_dma_tail_wait(")
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "tail-wait.c"
            executable = Path(temp) / "tail-wait.exe"
            source.write_text("#include <stdint.h>\n" + constants + HARNESS + body + CASES)
            subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                            "-I" + str(HERE.parent / "raw-slots"), str(source),
                            "-o", str(executable)], check=True)
            subprocess.run([str(executable)], check=True, timeout=10)

    def test_coordinator_wait_precedes_storage_and_first_write_marker(self):
        source = (HERE / "magic_runtime.inc").read_text()
        execute = function(source, "static void raw_magic_execute(void)\n")
        gate = "#if RAW_DMA_TAIL_WAIT\n    r=magic_dma_tail_wait(&available);\n    if(r) complete_storage(0x507U);\n#endif"
        self.assertIn(gate, execute)
        self.assertLess(execute.index("FIRST_SECTOR_WAIT_DONE"), execute.index(gate))
        self.assertLess(execute.index(gate), execute.index("P[RP_SLOT_BEGIN]"))
        self.assertLess(execute.index(gate), execute.index("magic_slots_write("))
        transport = function(source, "static int magic_transport(")
        self.assertLess(transport.index("P[RP_FIRST_WRITE]"),
                        transport.index("sd_write_blocks_stream_preerase("))
        wait = function(source, "static int magic_dma_tail_wait(")
        self.assertNotIn("HAL_", wait)
        self.assertNotIn("sd_", wait)
        self.assertNotIn("TRAILER_OFFSET", wait)
        self.assertIn("result=magic_publish(0,available);", wait)

    def test_default_disabled_and_trace_abi_unchanged(self):
        header = (HERE / "runtime.h").read_text()
        self.assertIn("#ifndef RAW_DMA_TAIL_WAIT\n#define RAW_DMA_TAIL_WAIT 0\n#endif", header)
        source = (HERE / "magic_runtime.inc").read_text()
        self.assertIn("#if RAW_FLASH || RAW_STANDBY || !RAW_DMA || !RAW_LINE_STREAM || !RAW_ASYNC_STOP", source)
        ids = {}
        for file in ("cycle_trace_events.h", "cycle_trace_sd.h"):
            for name, index in re.findall(r"#define CTE_(\w+) (\d+)", (HERE / file).read_text()):
                self.assertNotIn(int(index), ids)
                ids[int(index)] = name
        self.assertEqual(ids[48], "DMA_TAIL_WAIT_BEGIN")
        self.assertEqual(ids[49], "DMA_TAIL_WAIT_DONE")
        self.assertEqual(ids[47], "TERMINAL_READY")
        self.assertEqual(ids[64], "SD_INIT_BEGIN")
        self.assertTrue(all(i < 128 for i in ids))


HARNESS = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "magic_slots.h"
static volatile uint32_t raw_dma_tail_wait_proof[RAW_DMA_TAIL_WAIT_WORDS];
static uint32_t now, step, reads, calls, complete_after, fail_after, publish_error;
static uint32_t frame_validated, sensor_stopped, fault, fault_read, fault_on_read;
static uint32_t marks[2];
typedef struct { uint32_t CYCCNT; } typeof_timer;
static typeof_timer timer;
static typeof_timer *get_dwt(void) {
    timer.CYCCNT=now; now+=step; ++reads; return &timer;
}
#define DWT get_dwt()
#define CYCLE_MARK(name) (++marks[MARK_##name])
#define MARK_DMA_TAIL_WAIT_BEGIN 0
#define MARK_DMA_TAIL_WAIT_DONE 1
static uint32_t raw_capture_frame_validated(void) { return frame_validated; }
static uint32_t raw_capture_sensor_stopped(void) { return sensor_stopped; }
static uint32_t raw_capture_fault(void) {
    ++fault_read;
    return fault || (fault_on_read && fault_read>=fault_on_read);
}
static int magic_publish(void *context, uint32_t *available) {
    assert(!context); ++calls;
    if(fail_after && calls>=fail_after) return (int)publish_error;
    if(complete_after && calls>=complete_after) {
        sensor_stopped=1; *available=MAGIC_SLOTS_PADDED_BYTES;
    }
    return 0;
}
'''

CASES = r'''
static void reset(void) {
    memset((void *)raw_dma_tail_wait_proof,0xA5,sizeof(raw_dma_tail_wait_proof));
    now=1234;step=100000;reads=calls=complete_after=fail_after=publish_error=0;
    frame_validated=1;sensor_stopped=fault=fault_read=fault_on_read=0;
    marks[0]=marks[1]=0;
}
static void check(uint32_t outcome,uint32_t available,int result) {
    const volatile uint32_t *p=raw_dma_tail_wait_proof;
    assert(p[DTW_MAGIC]==RAW_DMA_TAIL_WAIT_MAGIC && p[DTW_VERSION]==1);
    assert(p[DTW_OUTCOME]==outcome && p[DTW_RESULT]==(uint32_t)result);
    assert(p[DTW_AVAILABLE_AFTER]==available && p[DTW_LIMIT]==4000000);
    assert(p[DTW_POLLS]==calls && p[DTW_ELAPSED]==(uint32_t)(p[DTW_END]-p[DTW_START]));
    assert(!p[DTW_RESERVED0] && !p[DTW_RESERVED1] && !p[DTW_RESERVED2]);
}
int main(void) {
    uint32_t available;
    reset();available=MAGIC_SLOTS_PADDED_BYTES;sensor_stopped=1;
    assert(!magic_dma_tail_wait(&available));check(DTW_ALREADY_FULL,available,0);
    assert(!calls && reads==1 && !marks[0] && !marks[1]);

    /* Even an almost complete prefix may not wait until FRAME is validated. */
    reset();available=MAGIC_SLOTS_PADDED_BYTES-512;frame_validated=0;
    assert(!magic_dma_tail_wait(&available));check(DTW_FRAME_PENDING,available,0);
    assert(!calls && reads==1 && !marks[0] && !marks[1]);

    reset();available=MAGIC_SLOTS_PADDED_BYTES-513;
    assert(!magic_dma_tail_wait(&available));check(DTW_PREFIX_SHORT,available,0);
    assert(!calls && reads==1 && !marks[0] && !marks[1]);

    reset();available=MAGIC_SLOTS_PADDED_BYTES-512;complete_after=3;
    assert(!magic_dma_tail_wait(&available));check(DTW_COMPLETED,available,0);
    assert(calls==3 && marks[0]==1 && marks[1]==1);
    assert(raw_dma_tail_wait_proof[DTW_ELAPSED]<4000000);

    reset();available=MAGIC_SLOTS_PADDED_BYTES-512;
    assert(!magic_dma_tail_wait(&available));check(DTW_TIMEOUT_PIO,available,0);
    assert(calls==39 && marks[0]==1 && marks[1]==1);
    assert(raw_dma_tail_wait_proof[DTW_ELAPSED]>=4000000);
    assert(raw_dma_tail_wait_proof[DTW_ELAPSED]<=4000000+step);

    reset();now=0xFFFF0000U;available=MAGIC_SLOTS_PADDED_BYTES-512;
    assert(!magic_dma_tail_wait(&available));check(DTW_TIMEOUT_PIO,available,0);
    assert(calls==39 && raw_dma_tail_wait_proof[DTW_END]<raw_dma_tail_wait_proof[DTW_START]);

    reset();now=0xFFFF0000U;available=MAGIC_SLOTS_PADDED_BYTES-512;complete_after=2;
    assert(!magic_dma_tail_wait(&available));check(DTW_COMPLETED,available,0);
    assert(calls==2);

    /* Camera fault before entry, then publisher camera/guard failures mid-wait. */
    reset();fault=1;available=MAGIC_SLOTS_PADDED_BYTES-512;
    assert(magic_dma_tail_wait(&available)==1);check(DTW_FAULT,available,1);
    assert(!calls && !marks[0] && !marks[1]);
    for(uint32_t failure=1;failure<=2;failure++) {
        reset();available=MAGIC_SLOTS_PADDED_BYTES-512;fail_after=2;publish_error=failure;
        assert(magic_dma_tail_wait(&available)==(int)failure);check(DTW_FAULT,available,(int)failure);
        assert(calls==2 && marks[0]==1 && marks[1]==1);
    }
    reset();available=MAGIC_SLOTS_PADDED_BYTES-512;fault_on_read=2;
    assert(magic_dma_tail_wait(&available)==1);check(DTW_FAULT,available,1);
    assert(calls==39 && marks[1]==1);
    puts("actual DMA tail-wait eligibility/deadline/fault cases passed");return 0;
}
'''


if __name__ == "__main__":
    unittest.main()
