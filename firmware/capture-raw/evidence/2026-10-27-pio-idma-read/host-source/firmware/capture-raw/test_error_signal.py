"""Run the actual failure pulse scheduler with a host platform model.

No debugger, peripheral, storage device or instrument is accessed. These tests
prove pulse count/timing decisions and fail-closed control flow, not hardware
time calibration, rail behavior, preserved SD contents or actual Standby.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <setjmp.h>
#include "error_signal.h"
static jmp_buf done;
static unsigned elapsed, calls, failed_call, can_begin;
int error_platform_begin(void) { return can_begin; }
void error_platform_led(uint32_t on) { printf("L %u %u\n", elapsed, on); }
int error_platform_delay(uint32_t ms) {
    calls++;
    if (calls==failed_call) return 0;
    elapsed+=ms;
    return 1;
}
void error_platform_end(void) { error_platform_led(0); printf("E %u\n",elapsed); longjmp(done,1); }
int main(int argc,char **argv) {
    if (argc!=4) return 2;
    unsigned code=(unsigned)strtoul(argv[1],0,0);
    failed_call=(unsigned)strtoul(argv[2],0,0);
    can_begin=(unsigned)strtoul(argv[3],0,0);
    if (!setjmp(done)) error_signal_shutdown(code);
    return 0;
}
'''


class ErrorSignalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("clang") or shutil.which("gcc")
        if not compiler:
            raise RuntimeError("host C compiler required")
        cls.temp = tempfile.TemporaryDirectory()
        out = Path(cls.temp.name)
        (out / "harness.c").write_text(HARNESS)
        cls.binary = out / "error-schedule.exe"
        subprocess.run([compiler, "-std=c11", "-O2", "-DERROR_SIGNAL_HOST_TEST=1",
                        "-I" + str(HERE), str(HERE / "error_signal.c"),
                        str(out / "harness.c"), "-o", str(cls.binary)], check=True,
                       capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_code(self, code, failed=0, begin=1):
        text = subprocess.check_output([str(self.binary), str(code), str(failed), str(begin)], text=True)
        events = [tuple(map(int, line.split()[1:])) for line in text.splitlines() if line.startswith("L ")]
        elapsed = int(text.splitlines()[-1].split()[1])
        return events, elapsed

    def test_all_codes_have_five_exact_sets_and_final_dark_period(self):
        for code in range(1, 9):
            with self.subTest(code=code):
                events, elapsed = self.run_code(code)
                expected = []
                now = 0
                for group in range(5):
                    for blink in range(code):
                        expected.append((now, 1))
                        now += 100
                        expected.append((now, 0))
                        now += 400 if blink + 1 < code or group == 4 else 2000
                expected.append((now, 0))  # Terminal shutdown explicitly leaves all LEDs off.
                self.assertEqual(events, expected)
                self.assertEqual(elapsed, 2500 * code + 6400)

    def test_invalid_codes_have_distinct_internal_fallback(self):
        expected = self.run_code(8)
        for code in (0, 9, 0xFFFFFFFF):
            self.assertEqual(self.run_code(code), expected)

    def test_platform_precondition_failure_shuts_down_without_unbounded_delay(self):
        self.assertEqual(self.run_code(4, begin=0), ([(0, 0)], 0))

    def test_stopped_timer_always_leaves_led_off_then_finishes(self):
        # Fail each delay in the longest supported sequence, including while lit.
        for delay in range(1, 81):
            with self.subTest(delay=delay):
                events, elapsed = self.run_code(8, failed=delay)
                self.assertEqual(events[-1][1], 0)
                self.assertLess(elapsed, 26400)
                self.assertLessEqual(sum(on for _, on in events), 40)

    def test_engine_uses_no_late_helpers_or_gated_peripheral_reads(self):
        source = (HERE / "error_signal.c").read_text()
        self.assertNotRegex(source, r"\b(?:CSI|DCMIPP|I2C2|SDMMC2|XSPI1|XSPIM)(?:_S)?\s*->")
        self.assertNotRegex(source, r"\b(?:HAL_\w+|sd_\w+|raw_\w+|malloc|printf)\s*\(")
        self.assertNotRegex(source, r"0x343[Ff]")
        self.assertNotIn("media_idle=", source)
        self.assertNotIn("NVIC_SystemReset", source)
        self.assertNotRegex(source, r"GPIOE->\w+\s*[^;]*<<\s*(?:6|12)")
        self.assertIn('section(".error_text")', source)
        self.assertIn("SCB_DisableICache();", source)
        self.assertIn("FPU_FPCCR_LSPACT_Msk", source)
        self.assertIn("stalled==100000U", source)
        self.assertIn("for (;;) { __DSB(); __WFI(); }", source)

    def test_nor_deselection_precedes_host_reset_without_sleep_command(self):
        source = (HERE / "error_signal.c").read_text()
        self.assertLess(source.index("GPION->BSRR=1UL << 1;"),
                        source.index("RCC->AHB5RSTSR=RCC_AHB5RSTSR_XSPI1RSTS;"))
        self.assertNotIn("0xB9", source)
        self.assertIn("BSEC->FVRw[124]", source)
        self.assertNotRegex(source, r"BSEC->FVRw\[124\]\s*=")


if __name__ == "__main__":
    unittest.main()
