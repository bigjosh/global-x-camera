"""Offline tests of completion.c with scripted MMIO; never imports bench tools.

The actual C control flow is compiled as C++ with mocked registers/intrinsics.
Only fixed proof addresses and terminal ARM assembly are adapted for the host.
This verifies selected fail-closed paths, not electrical timing or power entry.
The production source must also compile as ARM C with the pinned CMSIS headers.
"""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CMSIS = ROOT / "tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers/CMSIS"


def fixture(folder, mode):
    source = (HERE / "completion.c").read_text()
    header = (HERE / "completion.h").read_text()
    peripheral = (HERE / "peripherals.h").read_text()
    device = (CMSIS / "Device/ST/STM32N6xx/Include/stm32n657xx.h").read_text()
    core = (CMSIS / "Include/core_cm55.h").read_text()
    definitions = dict(re.findall(
        r"^#define\s+(\w+)\s+([^\r\n]+)",
        re.sub(r"/\*.*?\*/", "", device + "\n" + core, flags=re.S), re.M))
    names = set(re.findall(
        r"\b(?:RCC|PWR|SCB|ICB|DBGMCU|DWT|CoreDebug)_[A-Z]\w*", source))
    required = {}

    def add(name):
        if name in required or name not in definitions:
            return
        value = definitions[name].strip()
        required[name] = value
        for dep in re.findall(r"\b[A-Za-z_]\w*\b", value):
            add(dep)

    for name in names:
        add(name)
    header = header.replace("0x343F9C00U", "((uintptr_t)proof)")
    header = header.replace("0x343F9D00U", "((uintptr_t)peripheral_proof)")
    source = source.replace('#include "completion.h"',
                            '#include "mock.h"\n#include "completion.h"')

    def terminal(match):
        assembly = match.group(0)
        if '"wfi\\n"' in assembly:
            return 'host_wfi();'
        if "low_power_failure_idle" in assembly:
            return 'throw End{"failure"};'
        if "low_power_return_idle" in assembly:
            return 'throw End{"returned"};'
        if "status_led_sleep_idle" in assembly:
            return 'throw End{"awake"};'
        raise AssertionError("Unknown assembly in production source")

    source = re.sub(r"__asm volatile\(.*?\);", terminal, source, flags=re.S)
    registers = {}
    for block, member in re.findall(r"(\w+)->(\w+)", source):
        if block in ("RCC", "PWR", "SCB", "EXTI", "BSEC", "DBGMCU",
                     "SysTick", "ICB", "NVIC", "DWT", "CoreDebug", "GPIOG"):
            registers.setdefault(block, set()).add(member)
    registers["GPIOG"].add("BSRR")
    sizes = {"FVRw": 384, "SFSRx": 12, "OTPVLDRx": 12,
             "ICER": 16, "ICPR": 16, "ISER": 16, "ISPR": 16}
    structs = []
    for block, members in registers.items():
        declarations = [
            "Reg " + member + (f"[{sizes[member]}]" if member in sizes else "") + ";"
            for member in sorted(members)]
        structs.append("struct Mock" + block + " {" + "".join(declarations) + "};")
        structs.append(f"inline Mock{block} mock_{block};\n#define {block} (&mock_{block})")
    status = (ROOT / "tmp/bringup/capture-sd-v50-build-20261020/receiver/status_leds.h").read_text()
    led_enum = re.search(r"enum \{\s*LED_P_MAGIC.*?\};", status, re.S).group(0)
    mock = "\n".join([
        "#pragma once", "#include <cstdint>", "#include <cstring>",
        "#include <string>", "#include <iostream>",
        "#define _Static_assert static_assert",
        "struct End { const char* kind; };",
        "struct Reg { uint32_t value=0; operator uint32_t() const; "
        "Reg& operator=(uint32_t); Reg& operator=(const Reg& r){return *this=uint32_t(r);} "
        "Reg& operator|=(uint32_t v){return *this=uint32_t(*this)|v;} "
        "Reg& operator&=(uint32_t v){return *this=uint32_t(*this)&v;} };",
        *[f"#define {k} {v}" for k, v in required.items()],
        *structs,
        "inline uint32_t proof[64],peripheral_proof[64],led_proof[32];",
        "inline uint32_t primask=0,ipsr=0; inline int peripheral_error=0;",
        "inline bool pending_sticky=false,debug_sticky=false,bsec_enable_fail=false,"
        "pwr_enable_fail=false,wfi_returns=false,svos_sticky=false;",
        "inline unsigned peripheral_calls=0,mutations=0;",
        "inline void __disable_irq(){primask=1;} inline uint32_t __get_PRIMASK(){return primask;}",
        "inline uint32_t __get_IPSR(){return ipsr;}",
        "inline void __DSB(){} inline void __DMB(){} inline void __ISB(){} inline void __NOP(){}",
        "inline void host_wfi(){if(!wfi_returns)throw End{\"wfi\"};}",
        led_enum,
        "#define STATUS_LED_PROOF led_proof",
        "enum status_led_phase {STATUS_LED_OFF=0,STATUS_LED_ERROR=4};",
        "inline void status_led_set(status_led_phase p){GPIOG->ODR="
        "(p==STATUS_LED_OFF?0x501U:0x101U);}",
        "inline void status_led_proof_sample(unsigned n){led_proof[n]=DWT->CYCCNT;}",
    ])
    (folder / "mock.h").write_text(mock)
    (folder / "status_leds.h").write_text('#include "mock.h"\n')
    (folder / "completion.h").write_text(header)
    (folder / "peripherals.h").write_text(peripheral)
    (folder / "completion.c").write_text(source)
    return folder / "test.cpp"


HOST_TEST = r'''
#include "mock.h"
#include "peripherals.h"
#include "completion.h"
Reg::operator uint32_t() const {
    if(this==&DWT->CYCCNT) return ++const_cast<Reg*>(this)->value;
    return value;
}
Reg& Reg::operator=(uint32_t n) {
    ++mutations;
    if(this==&RCC->APB4ENSR2 && !bsec_enable_fail) RCC->APB4ENR2.value|=n;
    if(this==&RCC->AHB4ENSR && !pwr_enable_fail) RCC->AHB4ENR.value|=n;
    if(this==&RCC->STOPCCR) RCC->STOPCR.value &= ~n;
    if(this==&DBGMCU->CR && debug_sticky) n|=7U;
    if(this==&PWR->CPUCR) {
        n &= ~PWR_CPUCR_CSSF;
        if(svos_sticky)n|=PWR_CPUCR_SVOS;
    }
    if(this==&PWR->WKUPCR) PWR->WKUPSR.value &= ~n;
    if(this==&EXTI->RPR1 && pending_sticky) n=1U;
    value=n;
    return *this;
}
int camera_peripherals_shutdown(volatile camera_peripheral_proof_t* p) {
    ++peripheral_calls;
    if(p->word[0])throw End{"dirty-peripheral-proof"};
    p->word[0]=CAMERA_PERIPHERAL_MAGIC;
    return peripheral_error;
}
#include "completion.c"

int main(int argc,char**argv){
    std::string test=argc>1?argv[1]:"external";
    RCC->MISCENR.value=RCC_MISCENR_DBGEN;
    PWR->CR1.value=0;
    BSEC->SFSRx[3].value=BSEC->OTPVLDRx[3].value=1U<<28;
    DBGMCU->CR.value=7U;
    DWT->CTRL.value=DWT_CTRL_CYCCNTENA_Msk;
    CoreDebug->DEMCR.value=CoreDebug_DEMCR_TRCENA_Msk;
    for(unsigned i=0;i<64;++i)peripheral_proof[i]=0xAAAAAAAAU;
    if(test=="internal")PWR->CR1.value=PWR_CR1_SDEN;
    if(test=="peripheral-error")peripheral_error=99;
    if(test=="invalid-shadow")BSEC->SFSRx[3].value=0;
    if(test=="invalid-validity")BSEC->OTPVLDRx[3].value=0;
    if(test=="stop-reset")BSEC->FVRw[124].value=1U<<10;
    if(test=="standby-reset")BSEC->FVRw[124].value=1U<<11;
    if(test=="hardware-iwdg")BSEC->FVRw[124].value=1U;
    if(test=="pending")pending_sticky=true;
    if(test=="debug-sticky")debug_sticky=true;
    if(test=="bsec-clock")bsec_enable_fail=true;
    if(test=="pwr-clock")pwr_enable_fail=true;
    if(test=="pwr-reset")RCC->AHB4RSTR.value=RCC_AHB4RSTR_PWRRST;
    if(test=="debug-clock")RCC->MISCENR.value=0;
    if(test=="debug-reset")RCC->MISCRSTR.value=RCC_MISCRSTR_DBGRST;
    if(test=="cache")SCB->CCR.value=SCB_CCR_DC_Msk;
    if(test=="exception")ipsr=3;
    if(test=="wfi-return")wfi_returns=true;
    if(test=="readback"){PWR->CR1.value=PWR_CR1_SDEN;svos_sticky=true;}
    if(test=="timer")DWT->CTRL.value=0;
    try{status_led_complete_sleep();}
    catch(End e){
        uint32_t hash=2166136261U;
        for(unsigned w=1;w<62;++w)for(unsigned b=0;b<4;++b)
            hash=(hash^((proof[w]>>(8*b))&255))*16777619U;
        if(proof[0]!=LOW_POWER_PROOF_MAGIC || proof[1]!=1 || proof[2]!=64 ||
           proof[38]!=400000000U ||
           proof[62]!=hash || proof[63]!=LOW_POWER_PROOF_TERMINAL ||
           peripheral_calls!=1) return 90;
        if(test=="peripheral-error" && RCC->APB4ENSR2.value) return 91;
        std::cout<<e.kind<<" "<<proof[4]<<" "<<proof[5]<<" "
                 <<proof[19]<<" "<<proof[11]<<" "<<GPIOG->ODR.value<<"\n";
        return 0;
    }
    return 92;
}
'''


class CompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.binaries = {}
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            raise RuntimeError("A host C++ compiler is required for actual-source tests")
        for mode in range(4):
            folder = Path(cls.temp.name) / str(mode)
            folder.mkdir()
            source = fixture(folder, mode)
            source.write_text(HOST_TEST)
            binary = folder / "test.exe"
            p = subprocess.run([compiler, "-std=c++17", "-O0", "-Werror",
                                f"-DLOW_POWER_MODE={mode}",
                                "-DLOW_POWER_ENTRY_DELAY_US=100",
                                str(source), "-o", str(binary)],
                               capture_output=True, text=True)
            if p.returncode:
                raise AssertionError(p.stderr)
            cls.binaries[mode] = binary

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, mode, case):
        p = subprocess.run([str(self.binaries[mode]), case],
                           capture_output=True, text=True, check=True)
        values = p.stdout.strip().split()
        return values[0], *map(int, values[1:])

    def test_four_modes_arm_with_complete_checksums(self):
        for mode in range(4):
            with self.subTest(mode=mode):
                kind, state, error, cpucr, scr, led = self.run_case(mode, "external")
                self.assertEqual((kind, state, error, led),
                                 ("awake" if mode == 0 else "wfi", 40, 0, 0x501))
                self.assertEqual(bool(scr & 4), mode >= 2)
                if mode == 2:
                    self.assertEqual(cpucr & 0x10001, 0x10000)
                elif mode == 3:
                    self.assertEqual(cpucr & 0x10001, 1)

    def test_internal_smps_selects_stop_low(self):
        self.assertEqual(self.run_case(2, "internal")[3] & 0x10001, 0)

    def test_refused_peripheral_never_mutates_power_registers(self):
        for mode in range(4):
            self.assertEqual(self.run_case(mode, "peripheral-error")[:3],
                             ("failure", 255, 1))

    def test_deep_preconditions_fail_closed(self):
        cases = {"invalid-shadow": 4, "invalid-validity": 4,
                 "hardware-iwdg": 6, "pending": 9, "readback": 10}
        for mode in (2, 3):
            for case, error in cases.items():
                with self.subTest(mode=mode, case=case):
                    self.assertEqual(self.run_case(mode, case)[:3],
                                     ("failure", 255, error))
        self.assertEqual(self.run_case(2, "stop-reset")[:3], ("failure", 255, 5))
        self.assertEqual(self.run_case(3, "standby-reset")[:3], ("failure", 255, 5))
        self.assertEqual(self.run_case(2, "standby-reset")[2], 0)
        self.assertEqual(self.run_case(3, "stop-reset")[2], 0)

    def test_access_context_and_debug_gates(self):
        cases = {"pwr-clock": 2, "pwr-reset": 2, "bsec-clock": 3,
                 "debug-clock": 7, "debug-reset": 7, "debug-sticky": 8,
                 "cache": 12, "exception": 12, "timer": 14}
        for mode in (1, 2, 3):
            for case, error in cases.items():
                with self.subTest(mode=mode, case=case):
                    self.assertEqual(self.run_case(mode, case)[:3],
                                     ("failure", 255, error))

    def test_unexpected_wfi_return_is_red_awake_without_retry(self):
        for mode in (1, 2, 3):
            values = self.run_case(mode, "wfi-return")
            self.assertEqual(values[:3], ("returned", 50, 11))
            self.assertEqual(values[-1], 0x101)


class PrefixLengthTests(unittest.TestCase):
    """The >16-KiB receiver changes both MOVW halfwords after early recovery."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(HERE.parent))
        import build
        cls.builder = build

    def test_real_disassembled_movw_values_and_wrong_register(self):
        for raw, expected in ((bytes.fromhex("43f69423"), 14996),
                              (bytes.fromhex("44f21863"), 17944)):
            prefix = bytearray(0xB02)
            prefix[0xAFE:0xB02] = raw
            self.assertEqual(self.builder.decode_stage2_length(prefix), expected)
            prefix[0xB01] ^= 1  # r3 -> r2
            with self.assertRaises(AssertionError):
                self.builder.decode_stage2_length(prefix)

    def test_identity_still_rejects_early_code_and_external_literal_changes(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            old, new = bytearray(0xC00), bytearray(0xC00)
            old[0xAFE:0xB02] = bytes.fromhex("43f69423")
            new[0xAFE:0xB02] = bytes.fromhex("44f21863")
            lines = ["34180a76: f7ff fe89 bl 3418078c <recovery_gpio_park>"]
            for i in range(10):
                lines.append(f"{0x34180790+2*i:x}: ldr r0, [pc, #4] "
                             f"@ ({0x34180F40+4*i:x} <literal>)")
            (folder / "stage1.lst").write_text("\n".join(lines))
            self.assertEqual(len(self.builder.check_recovery_identity(
                folder, new, old, 17944)), 10)
            for offset in (0x100, 0xB40):
                changed = bytearray(new)
                changed[offset] ^= 1
                with self.assertRaises(AssertionError):
                    self.builder.check_recovery_identity(folder, changed, old, 17944)
            with self.assertRaises(AssertionError):
                self.builder.check_recovery_identity(folder, new, old, 14996)


if __name__ == "__main__":
    unittest.main()
