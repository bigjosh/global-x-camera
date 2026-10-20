"""Offline protocol tests of the actual driver with scripted register effects.

The driver is included unchanged in a C++ test translation unit so register
reads/writes can be intercepted. This models selected protocol states, not the
peripheral timing or electrical behavior. The production driver is separately
compiled as ARM C with the real pinned CMSIS headers.
"""
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
    device = (CMSIS / 'Device/ST/STM32N6xx/Include/stm32n657xx.h').read_text()
    core = (CMSIS / 'Include/core_cm55.h').read_text()
    macros = re.sub(r'/\*.*?\*/', '', device+'\n'+core, flags=re.S)
    definitions = dict(re.findall(r'^#define\s+(\w+)\s+([^\r\n]+)', macros, re.M))
    source = (HERE / 'sd_card.c').read_text() + (HERE / 'test_sd_driver.cpp').read_text()
    names = set(re.findall(r'\b(?:SDMMC|RCC|PWR|DWT|CoreDebug)_[A-Z]\w*', source))
    names.difference_update({'SDMMC_TypeDef', 'SDMMC2_S', 'RCC_S', 'PWR_S'})
    names.add('SDMMC2_BASE_S')
    required = {}

    def add(name):
        if name in required or name not in definitions:
            return
        value = definitions[name].split('/*')[0].strip()
        required[name] = value
        for dependency in re.findall(r'\b[A-Za-z_]\w*\b', value):
            add(dependency)

    for name in names:
        add(name)
    end = device.index('} SDMMC_TypeDef;') + len('} SDMMC_TypeDef;')
    start = device.rfind('typedef struct', 0, end)
    sd_type = re.sub(r'__(?:IO|I|O)\s+uint32_t', 'MockReg', device[start:end])
    return '\n'.join([
        '#pragma once', '#include <stdint.h>', '#include <stddef.h>',
        '#define _Static_assert static_assert',
        'struct MockReg { uint32_t value; operator uint32_t() const; '
        'MockReg& operator=(uint32_t); MockReg& operator|=(uint32_t); '
        'MockReg& operator&=(uint32_t); };',
        *[f'#define {name} {value}' for name, value in required.items()],
        sd_type,
        'struct MockRcc { MockReg CFGR1,CFGR2,PLL1CFGR1,PLL1CFGR2,PLL1CFGR3,'
        'IC1CFGR,IC2CFGR,DIVENR,HSICFGR,AHB5ENR,AHB4ENR,AHB4ENSR,'
        'CCIPR8,AHB5ENSR,AHB5RSTSR,AHB5RSTCR,AHB5ENCR; };',
        'struct MockGpio { MockReg MODER,OTYPER,OSPEEDR,PUPDR,IDR,BSRR,AFR[2]; };',
        'struct MockPwr { MockReg SVMCR2; };',
        'struct MockDwt { MockReg CTRL,CYCCNT; };',
        'struct MockDebug { MockReg DEMCR; };',
        'extern SDMMC_TypeDef test_sd; extern MockRcc test_rcc;',
        'extern MockGpio test_gpio_c,test_gpio_e; extern MockPwr test_pwr;',
        'extern MockDwt test_dwt; extern MockDebug test_debug;',
        '#define SDMMC2_S (&test_sd)', '#define RCC_S (&test_rcc)',
        '#define GPIOC_S (&test_gpio_c)', '#define GPIOE_S (&test_gpio_e)',
        '#define PWR_S (&test_pwr)', '#define DWT (&test_dwt)',
        '#define CoreDebug (&test_debug)',
        'static inline uint32_t __get_IPSR(void) {return 0;}',
        'static inline uint32_t __get_CONTROL(void) {return 0;}',
        'static inline void __DSB(void) {} static inline void __ISB(void) {}',
    ])


class SdDriverTests(unittest.TestCase):
    def test_scripted_register_protocol_and_failures(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler, 'Native C++ compiler required')
        with tempfile.TemporaryDirectory(prefix='sd-driver-') as temp:
            temp = Path(temp)
            (temp / 'stm32n657xx.h').write_text(mock_header())
            hook = temp / 'progress_hook.cpp'
            hook.write_text('extern "C" { unsigned sd_hook_calls=0; '
                            'void sd_progress(void) { ++sd_hook_calls; } }\n')
            executable = temp / 'sd-driver-test.exe'
            subprocess.run([compiler, '-std=c++17', '-O2', '-Wall', '-Wextra',
                            '-Werror', '-I', str(temp), '-I', str(HERE),
                            str(HERE/'test_sd_driver.cpp'), str(hook),
                            '-o', str(executable)],
                           check=True)
            completed = subprocess.run([str(executable)], text=True, capture_output=True)
            self.assertEqual(completed.returncode, 0, completed.stdout+completed.stderr)
            self.assertIn('13 protocol cases passed', completed.stdout)


if __name__ == '__main__':
    unittest.main()
