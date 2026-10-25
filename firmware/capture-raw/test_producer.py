"""Offline producer logic and transform checks; no bench or disks accessed."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import struct

HERE = Path(__file__).resolve().parent


class ProducerTests(unittest.TestCase):
    def test_compiled_boundaries(self):
        compiler = shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(compiler, "host C compiler required")
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / "producer-test.exe"
            subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                            str(HERE / "producer.c"), str(HERE / "test_producer.c"),
                            "-o", str(executable)], check=True)
            subprocess.run([str(executable)], check=True)

    def test_transform_rejects_unrecognized_capture(self):
        spec = importlib.util.spec_from_file_location("producer_transform_test", HERE / "producer_transform.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaises(ValueError):
            module.transform("an unrelated source file")

    def test_generated_failure_boundary_and_stale_line_clear(self):
        # Transform the pinned source without compiling or executing firmware.
        # Full-frame validation is forbidden inside every SD call, while async
        # STOP may record an error for handling after the outer call returns.
        sys.path.insert(0, str(HERE))
        try:
            spec = importlib.util.spec_from_file_location("raw_build_test", HERE / "build.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            source = module.transform_capture((module.BASE / "receiver/capture.c").read_text())
        finally:
            sys.path.remove(str(HERE))
        self.assertIn("raw_capture_fail(where,result);", source)
        self.assertNotIn("fast_failure_quiesce(where,result);", source)
        guard = source.index("if(raw_storage_transfer_active() && !capture_finalizing) return;")
        self.assertLess(guard, source.index("  if(capture_stop_pending)"))
        self.assertNotIn("RAW_LINE_STREAM && raw_storage_transfer_active()", source)
        clear = source.index("DCMIPP->CMFCR=DCMIPP_CMFCR_CP0LINEF;")
        self.assertLess(clear, source.index("HAL_DCMIPP_PIPE_EnableLineEvent(&hcam"))
        self.assertLess(clear, source.index("  arm_receiver();"))

    def test_failure_cleanup_preserves_sd_ownership(self):
        source = (HERE / "runtime.c").read_text()
        abort = source[source.index("static void abort_camera("):source.index("void raw_capture_fail(")]
        self.assertIn("RCC_APB5RSTSR_DCMIPPRSTS|RCC_APB5RSTSR_CSIRSTS", abort)
        self.assertIn("GPIOO->BSRR=1U<<21", abort)
        self.assertNotIn("SDMMC", abort)
        self.assertNotIn("CSI->", abort)
        self.assertNotIn("DCMIPP->", abort)
        cleanup = source[source.index("static void complete_storage(int result)\n{"):source.index("static void init_card(")]
        self.assertLess(cleanup.index("abort_camera("), cleanup.index("sd_deinit("))
        self.assertLess(cleanup.index("if(storage_call_depth || __get_IPSR())"), cleanup.index("sd_deinit("))
        self.assertNotIn("raw_card.controller_owned=", cleanup)
        self.assertNotIn("raw_card.media_idle=", cleanup)
        early = source[source.index("void raw_capture_fail("):source.index("static void snapshot(")]
        self.assertLess(early.index("0x343F9E3CU!=0x524C4F4BU"), early.index("complete_storage("))
        self.assertIn("terminal(0xF003U)", early)

    def test_runtime_never_commits_without_full_frame_and_stop(self):
        # Guard important handoff ordering; behavioral producer bounds above
        # execute actual C. This check prevents deleting the integration gates.
        source = (HERE / "runtime.c").read_text()
        wait = source.index("while(!raw_capture_frame_validated() || !raw_capture_sensor_stopped())")
        finish = source.index("SD_OPERATION(r,raw_slots_finish(")
        self.assertLess(wait, finish)
        self.assertIn("SD_OPERATION(r,raw_slots_append(", source)
        self.assertIn("if(raw_capture_fault()) complete_storage(0x503U);", source)
        self.assertIn("if(!count)", source)

    def test_boot_revokes_retained_late_code_authority(self):
        # Execute the actual dispatch prelude with retained diagnostic SRAM.
        # It must revoke a prior successful boot before the first fallible
        # initialization, while the RAM maintenance build remains unaffected.
        compiler = shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(compiler, "host C compiler required")
        source = (HERE / "runtime.c").read_text()
        dispatch = source.split("void raw_runtime_dispatch(void)\n{", 1)[1]
        prelude = dispatch.split("    for(unsigned i=0;i<RAW_PROOF_WORDS;", 1)[0]
        prelude = prelude.replace("*(volatile uint32_t *)0x343F9E3CU", "retained_marker")
        program = """#include <stdint.h>
#include <assert.h>
static volatile uint32_t retained_marker;
static unsigned barriers;
#define __DSB() (++barriers)
#define cycle_trace_init() ((void)0)
#define CYCLE_MARK(name) ((void)0)
static void boot_prelude(void) {
""" + prelude + """}
int main(void) {
    const uint32_t prior[] = {0x524C4F4BU, 0U, 0xFFFFFFFFU};
    for (unsigned i = 0; i < 3; ++i) {
        retained_marker = prior[i]; barriers = 0;
        boot_prelude();
#if RAW_FLASH
        assert(retained_marker != 0x524C4F4BU);
        assert(retained_marker == 0U && barriers == 1U);
#else
        assert(retained_marker == prior[i] && barriers == 0U);
#endif
    }
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as temp:
            c = Path(temp) / "boot-freshness.c"
            c.write_text(program)
            for flash in (0, 1):
                executable = Path(temp) / f"boot-freshness-{flash}.exe"
                subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                f"-DRAW_FLASH={flash}", str(c), "-o", str(executable)], check=True)
                subprocess.run([str(executable)], check=True)

    def test_snapshot_and_chunk_qualification(self):
        spec = importlib.util.spec_from_file_location("producer_verify_test", HERE / "verify_producer.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        frame = bytes(range(256)) * (module.FRAME_BYTES // 256) + bytes(range(module.FRAME_BYTES % 256))
        words = [0] * 104
        words[:16] = [0x50524431, 1, 1, 22, 1, 1, 0, module.FRAME_BYTES,
                      100, 200, 2200, 2300, 2400, 20 * 89600, 0, 20]
        for i in range(22):
            words[16 + 2*i:18 + 2*i] = [100*(i+1), (min(i+1, 21)-1)*89600]
        snapshots = bytearray()
        for i in range(20):
            offset = (i+1)*89600-512
            words[64+2*i:66+2*i] = [offset, 512]
            snapshots += frame[offset:offset+512]
        producer = struct.pack("<104I", *words)
        # Firstchunk starts on first publishedgroup; second starts afterFRAME.
        chunks = struct.pack("<16I", 300, 4000, 0, 175, 89600, 0x900, 0, 3700,
                             4100, 9000, 175, 3554, module.FRAME_BYTES, 0x900, 0, 4900)
        proof = dict(begin=0, frame_done=2300, chunk_count=2, chunk_overflow=0)
        self.assertTrue(module.verify(producer, snapshots, frame, chunks, proof)["passed"])
        snapshots[0] ^= 1
        with self.assertRaises(ValueError):
            module.verify(producer, snapshots, frame, chunks, proof)
        snapshots[0] ^= 1
        bad = bytearray(chunks)
        struct.pack_into("<I", bad, 16, 89599)
        with self.assertRaises(ValueError):
            module.verify(producer, snapshots, frame, bad, proof)


if __name__ == "__main__":
    unittest.main()
