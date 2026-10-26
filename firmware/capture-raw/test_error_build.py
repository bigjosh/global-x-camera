"""Offline error-profile admission, real injection dispatch and prefix boundaries.

No debugger, instruments or block devices are opened. ARM toolchain tests use
minimal temporary ELF fixtures to exercise the production relocation/linker
checks, not a parallel implementation of those checks.
"""
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

HERE = Path(__file__).resolve().parent


class ErrorBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(HERE))
        spec = importlib.util.spec_from_file_location("error_profile_builder_test", HERE / "build.py")
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)
        cls.integration = cls.builder.error_build
        cls.base = cls.builder.BASE / "staged"

    def refused_cli(self, options, message):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "must-not-exist"
            result = subprocess.run([sys.executable, str(HERE / "build.py"),
                "--out", str(output), *options], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn(message, result.stderr)
            self.assertFalse(output.exists(), "Rejected profile must not start building")

    def test_every_injected_code_is_refused_in_flash_and_standby(self):
        for code in range(1, 10):
            for target in ("--flash", "--standby"):
                with self.subTest(code=code, target=target):
                    self.refused_cli(["--magic-format", "--line-stream", "--error-blinks",
                        "--error-test-code", str(code), target],
                        "Injected error requires an explicit RAM-only")

    def test_error_options_require_explicit_layout_and_renderer(self):
        self.refused_cli(["--error-blinks"], "requires the selected magic-slot layout")
        self.refused_cli(["--magic-format", "--line-stream", "--error-test-code", "7"],
                         "Injected error requires an explicit RAM-only")
        for code in (-1, 10, 0xFFFFFFFF):
            self.refused_cli(["--magic-format", "--line-stream", "--error-blinks",
                              "--error-test-code", str(code)], "invalid choice")

    def test_actual_generated_injection_dispatch_and_request_gate(self):
        compiler = shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(compiler, "host C compiler required")
        program = INJECTION_HARNESS
        for code in range(1, 10):
            template = (f"static void inject_{code}(void) {{\n"
                "    status_led_boot_begin(); status_led_proof_init();\n}\n")
            program += self.integration.inject_error(template, code)
        program += INJECTION_CASES
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "dispatch.c"
            binary = Path(temp) / "dispatch.exe"
            source.write_text(program)
            subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                str(source), "-o", str(binary)], check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, timeout=10)

    def test_transforms_fail_closed_on_missing_or_duplicate_anchors(self):
        anchor = "    status_led_boot_begin(); status_led_proof_init();"
        for source in ("unrelated", anchor + "\n" + anchor):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "anchor mismatch"):
                self.integration.inject_error(source, 7)
        runtime = (HERE / "runtime.c").read_text()
        changed = self.integration.runtime_source(runtime)
        self.assertEqual(changed.count("error_signal_shutdown(code);"), 1)
        self.assertIn("if(result && operation==RAW_OP_CAPTURE)", changed)
        self.assertIn("P[RP_STATE]=15U", changed)
        self.assertNotIn("P[RP_RESULT]=0;", changed)
        include = '#include "runtime.h"'
        for source in (runtime.replace(include, ""),
                       runtime.replace(include, include + "\n" + include)):
            with self.subTest(anchor="runtime include"), self.assertRaisesRegex(ValueError, "anchor mismatch"):
                self.integration.runtime_source(source)

    def prefix_fixture(self, folder):
        original = (self.base / "stage1.bin").read_bytes()
        self.assertEqual(len(original), self.integration.PREFIX_BYTES)
        prefix = bytearray(original + bytes(128))
        prefix[0x101A] = 0x30  # Existing packed-RAW change, after recovery.
        prefix[0xE6:0xEC] = b"\x01\xf0\x9b\xb9\xfc\xe7"
        for offset in (0xC9C, 0x1354):
            prefix[offset:offset+4] = struct.pack("<I", 0x12345678)
        # The selected v66c archive omits its listing. The older frozen listing
        # contains the identical recovery instructions; prove their bytes before
        # using those symbol/literal annotations with the v66c binary fixture.
        listed = self.builder.ROOT / "firmware/capture-sd/evidence/2026-10-20-low-power/build/prefix"
        self.assertEqual((listed / "stage1.bin").read_bytes()[:0xAFE], original[:0xAFE])
        listing = (listed / "stage1.lst").read_text()
        listing += "\n341804e6: f001 b99b b.w 34181820 <error_stage1_bridge>\n"
        listing += "34181840 <error_signal_shutdown>:\n"
        (folder / "stage1.lst").write_text(listing)
        return original, bytes(prefix), listing

    def test_extended_prefix_restores_only_failure_bytes_for_legacy_checker(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            original, prefix, _ = self.prefix_fixture(folder)
            checker = Mock(return_value=[1, 2, 3])
            self.assertEqual(self.integration.check_prefix(folder, prefix, original, 15804, checker), [1,2,3])
            checker.assert_called_once()
            _, normalized, forwarded_original, size = checker.call_args.args
            self.assertEqual((len(normalized), forwarded_original, size), (5140, original, 15804))
            self.assertEqual(normalized[0xE6:0xEC], original[0xE6:0xEC])
            self.assertEqual(normalized[0x101A], 0x30)
            self.assertEqual(normalized[0xC9C:0xCA0], struct.pack("<I", 0x12345678))
            # The real historical guard independently checks its early-load
            # instruction and all out-of-line recovery literals.
            self.assertGreaterEqual(len(self.integration.check_prefix(folder, prefix,
                original, 15804, self.builder.check_recovery_identity)), 10)
            with self.assertRaises(AssertionError):
                self.integration.check_prefix(folder, prefix, original, 15808,
                                              self.builder.check_recovery_identity)

    def test_prefix_rejects_recovery_literal_branch_entry_and_size_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            original, prefix, listing = self.prefix_fixture(folder)
            for offset in (0, 0xE5, 0xEC, 0x390, 0xAFE, 0xC9B, 0xCA0, 0x101A, 0x1353, 0x1358, 5139):
                mutated = bytearray(prefix)
                mutated[offset] ^= 1
                with self.subTest(offset=offset), self.assertRaises(ValueError):
                    self.integration.check_prefix(folder, bytes(mutated), original, 15804, Mock())
            for length in (0, 5139, 5140, 0x1C01):
                candidate = (prefix + bytes(0x1C01))[:length]
                with self.subTest(length=length), self.assertRaisesRegex(ValueError, "prefix size"):
                    self.integration.check_prefix(folder, candidate, original, 15804, Mock())
            for changed in (listing.replace("b.w 34181820", "b.w 34181822"),
                            listing.replace("34181840 <error_signal_shutdown>", "34181842 <error_signal_shutdown>")):
                (folder / "stage1.lst").write_text(changed)
                with self.assertRaises(ValueError):
                    self.integration.check_prefix(folder, prefix, original, 15804, Mock())

    def prepare_prefix_sources(self, folder):
        for name in ("stage1.c", "stage1.ld"):
            (folder / name).write_bytes((self.base / name).read_bytes())
        return self.integration.prefix_sources(folder, HERE)

    def test_real_linker_fixed_entry_bridge_and_handler_overflow_guards(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            paths = self.prepare_prefix_sources(folder)
            self.assertEqual({p.name for p in paths}, {"error_bridge.c", "error_signal.c", "error_signal.h"})
            self.assertIn("result==17U?2U:8U", (folder / "error_bridge.c").read_text())
            self.assertEqual((folder / "error_signal.c").read_bytes(), (HERE / "error_signal.c").read_bytes())
            self.assertIn('b.w error_stage1_bridge', (folder / "stage1.c").read_text())
            for bridge_size, handler_size, expected in ((32,0x7C0,None),
                (33,0x7C0,"Error bridge overflow"), (32,0x7C1,"Error handler overflow")):
                assembly = f'''.syntax unified
.thumb
.section .text.entry,"ax",%progbits
.global Stage1_Reset_Handler
Stage1_Reset_Handler: b .
.section .error_bridge,"ax",%progbits
.space {bridge_size}
.section .error_text,"ax",%progbits
.global error_signal_shutdown
error_signal_shutdown:
.space {handler_size}
'''
                source = folder / "fixture.s"
                source.write_text(assembly)
                result = subprocess.run([str(self.builder.TC / "arm-none-eabi-gcc.exe"),
                    "-mcpu=cortex-m55", "-mthumb", "-nostdlib", "-T", str(folder / "stage1.ld"),
                    str(source), "-o", str(folder / "fixture.elf")], capture_output=True, text=True)
                with self.subTest(bridge_size=bridge_size, handler_size=handler_size):
                    if expected:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn(expected, result.stderr)
                    else:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        symbols = subprocess.check_output([str(self.builder.TC / "arm-none-eabi-nm.exe"),
                            str(folder / "fixture.elf")], text=True)
                        self.assertRegex(symbols, r"34181840 [A-Za-z] error_signal_shutdown")

    def crc_fixture(self, folder, length):
        source = folder / "fixture.s"
        source.write_text(f'''.syntax unified
.thumb
.section .text,"ax",%progbits
.space 0xc9c
.word 0x3e97c7f7
.space 0x1354-0xca0
.word 0x3e97c7f7
.space {length}-0x1358
''')
        (folder / "fixture.ld").write_text("SECTIONS { .text 0x34180400 : { *(.text) } }")
        subprocess.run([str(self.builder.TC / "arm-none-eabi-gcc.exe"), "-mcpu=cortex-m55", "-mthumb",
            "-nostdlib", "-T", str(folder / "fixture.ld"), str(source), "-o", str(folder / "stage1.elf")],
            check=True, capture_output=True, text=True)
        subprocess.run([str(self.builder.TC / "arm-none-eabi-objcopy.exe"), "-O", "binary",
            str(folder / "stage1.elf"), str(folder / "stage1.bin")], check=True)
        listing = subprocess.check_output([str(self.builder.TC / "arm-none-eabi-objdump.exe"), "-d",
                                           str(folder / "stage1.elf")], text=True)
        (folder / "stage1.lst").write_text(listing)
        return (folder / "stage1.bin").read_bytes()

    def test_real_elf_crc_relocation_accepts_exact_lower_and_upper_length_limits(self):
        for length in (5140, 0x1C00):
            with self.subTest(length=length), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                prefix = self.crc_fixture(folder, length)
                self.assertEqual(len(prefix), length)
                relocated, proof = self.builder.relocate_prefix_crc(folder, prefix, 0x3E97C7F7, 0x12345678)
                changes = {i for i,(a,b) in enumerate(zip(prefix,relocated)) if a!=b}
                self.assertEqual(changes, set(range(0xC9C,0xCA0)) | set(range(0x1354,0x1358)))
                self.assertEqual(proof["literal_offsets"], [0xC9C,0x1354])
                self.assertEqual((folder / "stage1-unrelocated.bin").read_bytes(), prefix)
                self.assertEqual((folder / "stage1.bin").read_bytes(), relocated)

    def test_crc_relocation_refuses_length_constant_or_literal_alias_drift_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for length, constant in ((5139,0x3E97C7F7),(0x1C01,0x3E97C7F7),(5140,0x11111111)):
                with self.subTest(length=length, constant=constant), self.assertRaisesRegex(ValueError, "geometry"):
                    self.builder.relocate_prefix_crc(folder, bytes(length), constant, 0)
                self.assertEqual(list(folder.iterdir()), [])
            prefix = bytearray(5140)
            for offset in (0xC9C,0x1354,0x1400):
                struct.pack_into("<I", prefix, offset, 0x3E97C7F7)
            with self.assertRaisesRegex(ValueError, "only at its two"):
                self.builder.relocate_prefix_crc(folder, bytes(prefix), 0x3E97C7F7, 0)
            self.assertEqual(list(folder.iterdir()), [])


INJECTION_HARNESS = r'''
#include <assert.h>
#include <stdint.h>
#include <setjmp.h>
static uint32_t request[16],terminal_result,direct_code,boot_calls,proof_calls;
#define Q request
#define SD_ERR_COMMAND_TIMEOUT 7U
#define MAGIC_SLOTS_ERR_IO 4U
#define MAGIC_SLOTS_ERR_FULL 5U
static struct { uint32_t error; } raw_magic_slots;
static jmp_buf exit_point;
static void status_led_boot_begin(void) { boot_calls++; }
static void status_led_proof_init(void) { proof_calls++; }
__attribute__((noreturn)) static void terminal(uint32_t result) { terminal_result=result; longjmp(exit_point,1); }
__attribute__((noreturn)) static void error_signal_shutdown(uint32_t code) { direct_code=code; longjmp(exit_point,1); }
'''
INJECTION_CASES = r'''
static void invoke(void (*entry)(void),uint32_t request_code,uint32_t expected_terminal,
                   uint32_t expected_direct,uint32_t expected_slot) {
    request[6]=request_code;terminal_result=0;direct_code=0;
    raw_magic_slots.error=0;boot_calls=0;proof_calls=0;
    if(!setjmp(exit_point)) entry();
    assert(boot_calls==1 && proof_calls==1);
    assert(terminal_result==expected_terminal && direct_code==expected_direct);
    assert(raw_magic_slots.error==expected_slot);
}
int main(void) {
    void (*entries[])(void)={inject_1,inject_2,inject_3,inject_4,inject_5,inject_6,inject_7,inject_8};
    const uint32_t terminal_codes[]={0,0x101,0x501,0x207,0x334,0,0x325,0xF003};
    for(unsigned i=0;i<8;i++) {
        invoke(entries[i],0,0,0,0);
        invoke(entries[i],7,0,0,0);
        invoke(entries[i],0x45525231U,terminal_codes[i],i==0||i==5?i+1:0,i==6?5:0);
        invoke(inject_9,i+1,terminal_codes[i],i==0||i==5?i+1:0,i==6?5:0);
    }
    invoke(inject_9,0,0,0,0);invoke(inject_9,9,0,0,0);invoke(inject_9,0x45525231U,0,0,0);
    return 0;
}
'''


if __name__ == "__main__":
    unittest.main()
