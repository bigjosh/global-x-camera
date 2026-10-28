"""Offline tests of the actual isolated IC5 helper, without hardware access."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CMSIS = ROOT / 'tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers/CMSIS'


def mock_header():
    source = (HERE/'sd_clock_profile.h').read_text() + (HERE/'test_sd_clock_profile.cpp').read_text()
    device = (CMSIS/'Device/ST/STM32N6xx/Include/stm32n657xx.h').read_text()
    definitions = dict(re.findall(r'^#define\s+(\w+)\s+([^\r\n]+)',
                                 re.sub(r'/\*.*?\*/', '', device, flags=re.S), re.M))
    required = {}
    def add(name):
        if name in required or name not in definitions:
            return
        value = definitions[name].strip()
        required[name] = value
        for dependency in re.findall(r'\b[A-Za-z_]\w*\b', value):
            add(dependency)
    for name in set(re.findall(r'\bRCC_[A-Z]\w*', source)) - {'RCC_S'}:
        add(name)
    fields = sorted(set(re.findall(r'RCC_S->(\w+)', source)))
    return '\n'.join([
        '#pragma once', '#include <stdint.h>', '#define _Static_assert static_assert',
        'struct MockReg { uint32_t value; operator uint32_t() const; MockReg& operator=(uint32_t); };',
        *[f'#define {key} {value}' for key, value in required.items()],
        'struct MockRcc { MockReg ' + ','.join(fields) + '; };',
        'extern MockRcc test_rcc;', '#define RCC_S (&test_rcc)',
        'static inline void __DSB(void) {} static inline void __ISB(void) {}',
    ])


class ClockProfileTests(unittest.TestCase):
    def test_actual_helper_ownership_failures_and_bounded_restore(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='sd-clock-') as temp:
            temp = Path(temp)
            (temp/'stm32n657xx.h').write_text(mock_header())
            exe = temp/'test.exe'
            subprocess.run([compiler, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-I'+str(temp), '-I'+str(HERE), str(HERE/'test_sd_clock_profile.cpp'),
                            '-o', str(exe)], check=True)
            p = subprocess.run([str(exe)], text=True, capture_output=True)
            self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
            self.assertIn('bounded cleanup cases passed', p.stdout)

    def test_arm_c_with_actual_cmsis(self):
        compiler = Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/') / (
            'com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.'
            '12.3.rel1.win32_1.0.200.202406191623/tools/bin/arm-none-eabi-gcc.exe')
        self.assertTrue(compiler.is_file())
        with tempfile.TemporaryDirectory(prefix='sd-clock-arm-') as temp:
            temp = Path(temp)
            unit = temp/'clock.c'
            unit.write_text('#include "stm32n657xx.h"\n#include "sd_clock_profile.h"\n'
                            'int acquire(void) { return sd_review_clock_acquire(); }\n'
                            'int release(void) { return sd_review_clock_release(); }\n')
            subprocess.run([str(compiler), '-std=c11', '-Os', '-Wall', '-Wextra', '-Werror',
                            '-mcpu=cortex-m55', '-mthumb', '-DSTM32N657xx', '-DCPU_IN_SECURE_STATE',
                            '-DSD_HIGH_SPEED=1', '-DSD_REVIEW_PROFILE=1', '-I'+str(HERE),
                            '-I'+str(CMSIS/'Include'), '-I'+str(CMSIS/'Device/ST/STM32N6xx/Include'),
                            '-c', str(unit), '-o', str(temp/'clock.o')], check=True)


if __name__ == '__main__':
    unittest.main()
