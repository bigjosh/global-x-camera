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
    source += (HERE / 'sd_clock_profile.h').read_text()
    names = set(re.findall(r'\b(?:SDMMC|RCC|PWR|DWT|CoreDebug|SCB|RIFSC|SysTick|DBGMCU|SYSCFG)_[A-Z]\w*', source))
    names.difference_update({'SDMMC_TypeDef', 'SDMMC2_S', 'RCC_S', 'PWR_S','DBGMCU_S','SYSCFG_S'})
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
        'IC1CFGR,IC2CFGR,DIVENR,HSICFGR,AHB5ENR,AHB4ENR,AHB4ENSR,AHB3ENR,'
        'CCIPR8,AHB5ENSR,AHB5RSTSR,AHB5RSTCR,AHB5ENCR,MEMLPENR,AHB3LPENR,AHB5LPENR,'
        'BUSLPENR,MISCENR,MISCRSTR,APB4ENR2,APB4ENSR2,APB4RSTR2,CR,SR,IC5CFGR,CCIPR5,CCIPR7,DIVENSR,DIVENCR; };',
        'struct MockGpio { MockReg MODER,OTYPER,OSPEEDR,PUPDR,IDR,BSRR,AFR[2]; };',
        'struct MockPwr { MockReg SVMCR2,SVMCR3; };',
        'struct MockSyscfg { MockReg VDDIO5CCCR; }; extern MockSyscfg test_syscfg;',
        'struct MockDwt { MockReg CTRL,CYCCNT; };',
        'struct MockDebug { MockReg DEMCR; };',
        'struct MockDbgMcu { MockReg CR; }; extern MockDbgMcu test_dbgmcu;',
        'struct MockScb { MockReg CCR,SCR; }; struct MockRif { MockReg RIMC_ATTRx[16],RISC_SECCFGRx[6]; };',
        'struct MockSysTick { MockReg CTRL,LOAD; }; extern MockSysTick test_systick;',
        'extern SDMMC_TypeDef test_sd; extern MockRcc test_rcc;',
        'extern MockGpio test_gpio_c,test_gpio_e; extern MockPwr test_pwr;',
        'extern MockDwt test_dwt; extern MockDebug test_debug;',
        'extern MockScb test_scb; extern MockRif test_rif;',
        '#define SDMMC2_S (&test_sd)', '#define RCC_S (&test_rcc)',
        '#define GPIOC_S (&test_gpio_c)', '#define GPIOE_S (&test_gpio_e)',
        '#define PWR_S (&test_pwr)', '#define SYSCFG_S (&test_syscfg)', '#define DWT (&test_dwt)',
        '#define CoreDebug (&test_debug)',
        '#define DBGMCU_S (&test_dbgmcu)',
        '#undef RIFSC_S', '#define RIFSC_S (&test_rif)', '#define SCB (&test_scb)',
        '#define SysTick (&test_systick)',
        'extern uint32_t test_primask,test_basepri,test_faultmask;',
        'static inline uint32_t __get_IPSR(void) {return 0;}',
        'static inline uint32_t __get_CONTROL(void) {return 0;}',
        'static inline uint32_t __get_PRIMASK(void) {return test_primask;}',
        'static inline uint32_t __get_BASEPRI(void) {return test_basepri;}',
        'static inline uint32_t __get_FAULTMASK(void) {return test_faultmask;}',
        'void test_wfi(void); static inline void __WFI(void) {test_wfi();}',
        'static inline void __DSB(void) {} static inline void __ISB(void) {}',
    ])


class SdDriverTests(unittest.TestCase):
    def run_scripted_register_protocol_and_failures(self, width, speed=3, compensation=0, negedge=0, initial_negedge=0, review_profile=0, high_speed=0, mixed_slew=0, high_fixed=0, combined=0, idma_read=0, startup_opt=0, early_run_clock=0):
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
                            '-Werror', f'-DSD_BUS_WIDTH={width}', f'-DSD_GPIO_SPEED={speed}',
                            f'-DSD_FIXED_COMPENSATION={compensation}',
                            f'-DSD_CLOCK_NEGEDGE={negedge}',
                            f'-DSD_CLOCK_NEGEDGE_INIT={initial_negedge}',
                            f'-DSD_REVIEW_PROFILE={review_profile}', f'-DSD_HIGH_SPEED={high_speed}',
                            f'-DSD_HIGH_SPEED_MIXED_SLEW={mixed_slew}',
                            f'-DSD_HIGH_SPEED_FIXED_COMPENSATION={high_fixed}',
                            f'-DSD_IDMA_READ={idma_read}',
                            f'-DSD_STARTUP_OPT={startup_opt}',
                            f'-DSD_EARLY_RUN_CLOCK={early_run_clock}',
                            f'-DSD_HIGH_SPEED_COMBINED_ELECTRICAL={combined}',
                            '-I', str(temp), '-I', str(HERE),
                            str(HERE/('test_sd_early_clock.cpp' if early_run_clock else 'test_sd_startup.cpp' if startup_opt else 'test_sd_idma_read.cpp' if idma_read else 'test_sd_high_speed.cpp' if high_speed else 'test_sd_driver.cpp')), str(hook),
                            '-o', str(executable)],
                           check=True)
            completed = subprocess.run([str(executable)], text=True, capture_output=True)
            self.assertEqual(completed.returncode, 0, completed.stdout+completed.stderr)
            self.assertIn('protocol cases passed', completed.stdout)

    def test_early_run_clock_protocol_and_failures(self):
        self.run_scripted_register_protocol_and_failures(4, negedge=1, initial_negedge=1,
            review_profile=1, startup_opt=1, early_run_clock=1)

    def test_arm_early_run_clock_compile_and_disabled_equivalence(self):
        from test_cycle_trace_driver import ARM_BIN, allocatable_sections
        with tempfile.TemporaryDirectory(prefix='sd-early-arm-') as temp:
            objects=[]
            for option in (None,0,1):
                obj=Path(temp)/f'early-{option}.o'
                subprocess.run([str(ARM_BIN/'arm-none-eabi-gcc.exe'), '-std=c11', '-Os',
                    '-Wall','-Wextra','-Werror','-mcpu=cortex-m55','-mthumb',
                    '-DSTM32N657xx','-DCPU_IN_SECURE_STATE','-DSD_BUS_WIDTH=4',
                    '-DSD_REVIEW_PROFILE=1','-DSD_STARTUP_OPT=1',
                    '-DSD_CLOCK_NEGEDGE=1','-DSD_CLOCK_NEGEDGE_INIT=1',
                    *([] if option is None else [f'-DSD_EARLY_RUN_CLOCK={option}']),
                    '-I'+str(CMSIS/'Include'),'-I'+str(CMSIS/'Device/ST/STM32N6xx/Include'),
                    '-c',str(HERE/'sd_card.c'),'-o',str(obj)],check=True)
                objects.append(allocatable_sections(obj))
            self.assertEqual(objects[0],objects[1])
            self.assertNotEqual(objects[0],objects[2])

    def test_startup_review_protocol_and_failures(self):
        self.run_scripted_register_protocol_and_failures(4, negedge=1, initial_negedge=1,
            review_profile=1, startup_opt=1)

    def test_startup_high_speed_protocol_and_failures(self):
        self.run_scripted_register_protocol_and_failures(4, negedge=1, initial_negedge=1,
            review_profile=1, high_speed=1, startup_opt=1)

    def test_arm_startup_compile_with_real_cmsis(self):
        compiler = Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/') / (
            'com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.'
            '12.3.rel1.win32_1.0.200.202406191623/tools/bin/arm-none-eabi-gcc.exe')
        with tempfile.TemporaryDirectory(prefix='sd-startup-arm-') as temp:
            for high_speed in (0, 1):
                subprocess.run([str(compiler), '-std=c11', '-Os', '-Wall', '-Wextra', '-Werror',
                    '-mcpu=cortex-m55', '-mthumb', '-DSTM32N657xx', '-DCPU_IN_SECURE_STATE',
                    '-DSD_BUS_WIDTH=4', '-DSD_REVIEW_PROFILE=1', '-DSD_STARTUP_OPT=1',
                    f'-DSD_HIGH_SPEED={high_speed}', '-DSD_CLOCK_NEGEDGE=1',
                    '-DSD_CLOCK_NEGEDGE_INIT=1',
                    '-I'+str(CMSIS/'Include'), '-I'+str(CMSIS/'Device/ST/STM32N6xx/Include'),
                    '-c', str(HERE/'sd_card.c'), '-o', str(Path(temp)/'sd_card.o')], check=True)

    def test_idma_read_review_protocol_and_failures(self):
        self.run_scripted_register_protocol_and_failures(4, review_profile=1, idma_read=1)

    def test_idma_read_high_speed_protocol_and_failures(self):
        self.run_scripted_register_protocol_and_failures(4, compensation=1, negedge=1,
            initial_negedge=1, review_profile=1, high_speed=1, high_fixed=1, idma_read=1)

    def test_high_speed_switch_protocol_and_failures(self):
        self.run_scripted_register_protocol_and_failures(4,negedge=1,initial_negedge=1,review_profile=1,high_speed=1)

    def test_high_speed_mixed_slew_protocol_and_failures(self):
        self.run_scripted_register_protocol_and_failures(4,negedge=1,initial_negedge=1,review_profile=1,high_speed=1,mixed_slew=1)

    def test_high_speed_fixed_compensation_protocol_and_failures(self):
        self.run_scripted_register_protocol_and_failures(4,compensation=1,negedge=1,initial_negedge=1,review_profile=1,high_speed=1,high_fixed=1)

    def test_high_speed_combined_electrical_protocol_and_failures(self):
        self.run_scripted_register_protocol_and_failures(4,compensation=1,negedge=1,initial_negedge=1,review_profile=1,high_speed=1,mixed_slew=1,high_fixed=1,combined=1)

    def test_one_bit_protocol_and_failures(self):
        self.run_scripted_register_protocol_and_failures(1)

    def test_four_bit_protocol_and_failures(self):
        self.run_scripted_register_protocol_and_failures(4)

    def test_low_slew_one_bit_protocol_and_failures(self):
        self.run_scripted_register_protocol_and_failures(1,0)

    def test_low_slew_four_bit_protocol_and_failures(self):
        self.run_scripted_register_protocol_and_failures(4,0)

    def test_fixed_compensation_protocol_and_failure_gates(self):
        self.run_scripted_register_protocol_and_failures(4,3,1)

    def test_negedge_protocol_and_failure_gates(self):
        self.run_scripted_register_protocol_and_failures(4,negedge=1)

    def test_initial_negedge_and_125mhz_protocol_and_failure_gates(self):
        self.run_scripted_register_protocol_and_failures(4,negedge=1,initial_negedge=1)

    def test_review_one_bit_protocol_and_failure_gates(self):
        self.run_scripted_register_protocol_and_failures(1,review_profile=1)

    def test_review_four_bit_protocol_and_failure_gates(self):
        self.run_scripted_register_protocol_and_failures(4,review_profile=1)

    def test_review_initial_negedge_protocol_and_failure_gates(self):
        self.run_scripted_register_protocol_and_failures(4,negedge=1,initial_negedge=1,review_profile=1)

    def test_medium_slew_protocol_and_failure_gates(self):
        self.run_scripted_register_protocol_and_failures(4,speed=1)

    def test_high_slew_protocol_and_failure_gates(self):
        self.run_scripted_register_protocol_and_failures(4,speed=2)

    def test_negedge_medium_slew_protocol_and_failure_gates(self):
        self.run_scripted_register_protocol_and_failures(4,speed=1,negedge=1)

    def test_negedge_high_slew_protocol_and_failure_gates(self):
        self.run_scripted_register_protocol_and_failures(4,speed=2,negedge=1)

    def test_arm_c_compile_with_real_cmsis(self):
        compiler = Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/') / (
            'com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.'
            '12.3.rel1.win32_1.0.200.202406191623/tools/bin/arm-none-eabi-gcc.exe')
        self.assertTrue(compiler.is_file(), 'Pinned ARM toolchain required')
        with tempfile.TemporaryDirectory(prefix='sd-driver-arm-') as temp:
            for width,speed,compensation,negedge,initial_negedge,review_profile,high_speed,mixed_slew,high_fixed in [tuple(x)+(0,0,0,0) for x in ((1,3,0,0,0),(4,3,0,0,0),(1,0,0,0,0),(4,0,0,0,0),(4,3,1,0,0),
                    (4,3,0,1,0),(4,1,0,0,0),(4,2,0,0,0),(4,1,0,1,0),(4,2,0,1,0),(4,3,0,1,1))]+[(4,3,0,1,1,1,0,0,0),(4,3,0,1,1,1,1,0,0),(4,3,0,1,1,1,1,1,0),(4,3,1,1,1,1,1,0,1)]:
                subprocess.run([str(compiler), '-std=c11', '-Os', '-Wall', '-Wextra',
                    '-Werror', '-mcpu=cortex-m55', '-mthumb', '-DSTM32N657xx',
                    f'-DSD_BUS_WIDTH={width}',f'-DSD_GPIO_SPEED={speed}',
                    f'-DSD_FIXED_COMPENSATION={compensation}',
                    f'-DSD_CLOCK_NEGEDGE={negedge}',
                    f'-DSD_CLOCK_NEGEDGE_INIT={initial_negedge}',
                    f'-DSD_REVIEW_PROFILE={review_profile}',f'-DSD_HIGH_SPEED={high_speed}',
                    f'-DSD_HIGH_SPEED_MIXED_SLEW={mixed_slew}',
                    f'-DSD_HIGH_SPEED_FIXED_COMPENSATION={high_fixed}',
                    '-DCPU_IN_SECURE_STATE', '-I'+str(CMSIS/'Include'),
                    '-I'+str(CMSIS/'Device/ST/STM32N6xx/Include'),
                    '-c', str(HERE/'sd_card.c'), '-o', str(Path(temp)/'sd_card.o')], check=True)

    def test_arm_idma_read_compile_with_real_cmsis(self):
        compiler = Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/') / (
            'com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.'
            '12.3.rel1.win32_1.0.200.202406191623/tools/bin/arm-none-eabi-gcc.exe')
        with tempfile.TemporaryDirectory(prefix='sd-idma-read-arm-') as temp:
            for high_speed in (0, 1):
                subprocess.run([str(compiler), '-std=c11', '-Os', '-Wall', '-Wextra', '-Werror',
                    '-mcpu=cortex-m55', '-mthumb', '-DSTM32N657xx', '-DCPU_IN_SECURE_STATE',
                    '-DSD_BUS_WIDTH=4', '-DSD_REVIEW_PROFILE=1', '-DSD_IDMA_READ=1',
                    f'-DSD_HIGH_SPEED={high_speed}', f'-DSD_CLOCK_NEGEDGE={high_speed}',
                    f'-DSD_CLOCK_NEGEDGE_INIT={high_speed}',
                    f'-DSD_FIXED_COMPENSATION={high_speed}',
                    f'-DSD_HIGH_SPEED_FIXED_COMPENSATION={high_speed}',
                    '-I'+str(CMSIS/'Include'), '-I'+str(CMSIS/'Device/ST/STM32N6xx/Include'),
                    '-c', str(HERE/'sd_card.c'), '-o', str(Path(temp)/'sd_card.o')], check=True)


if __name__ == '__main__':
    unittest.main()
