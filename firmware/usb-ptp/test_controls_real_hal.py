"""Canonical sampler against ST's actual ADC/ADCEx, with host register side effects.

Uses the local Cube SDK when present, or GLOBAL_X_HAL (driver root) and
GLOBAL_X_CMSIS (CMSIS root). Requires a native clang/gcc and 64-bit Linux or
Windows. No cross compiler, instrument library, programmer or device is used.
The driver sources are compiled unchanged; this does not qualify analog
settling, physical pin direction, or actual startup timing.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SDK = ROOT / 'tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers'
HAL = Path(os.environ.get('GLOBAL_X_HAL', str(SDK / 'STM32N6xx_HAL_Driver')))
CMSIS = Path(os.environ.get('GLOBAL_X_CMSIS', str(ROOT / 'firmware/capture-sd/evidence/2026-10-20-hardware/dependencies/st/STM32Cube_FW_N6/Drivers/CMSIS')))


class RealHALTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which('clang') or shutil.which('gcc')
        if not cls.compiler or sys.platform not in ('win32', 'linux'):
            raise unittest.SkipTest('Native clang/gcc on 64-bit Windows or Linux required')
        if not (HAL / 'Src/stm32n6xx_hal_adc.c').exists():
            raise unittest.SkipTest('Set GLOBAL_X_HAL to the STM32N6 HAL driver root')
        if not (CMSIS / 'Device/ST/STM32N6xx/Include/stm32n657xx.h').exists():
            raise unittest.SkipTest('Set GLOBAL_X_CMSIS to the STM32N6 CMSIS root')
        cls.temp = tempfile.TemporaryDirectory(prefix='controls-real-hal-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.build_dir = Path(cls.temp.name)
        cls.normal = cls.compile(HERE / 'capture_controls_adc.c', 'normal')

    @classmethod
    def compile(cls, sampler, name):
        exe = cls.build_dir / (name + '.exe')
        includes = [HERE / 'hal_model/fake', HERE / 'hal_model', HERE, HAL / 'Inc',
                    CMSIS / 'Device/ST/STM32N6xx/Include', CMSIS / 'Include']
        cmd = [cls.compiler, '-std=gnu11', '-O1', '-w', '-ffunction-sections',
               '-Wl,--gc-sections', '-D__ARM_FEATURE_CMSE=3', '-DSTM32N657xx', '-DUSE_HAL_DRIVER',
               '-DADC_MODEL_STRICT=1',
               *('-I' + str(p) for p in includes), str(HERE / 'hal_model/controls_model.c'),
               str(sampler), str(HERE / 'capture_controls_map.c'),
               str(HAL / 'Src/stm32n6xx_hal_adc.c'), str(HAL / 'Src/stm32n6xx_hal_adc_ex.c'), '-o', str(exe)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return exe

    def run_case(self, fault='none', exposure=2177, gain=1781, *, error=0, executable=None):
        result = subprocess.run([str(executable or self.normal), fault, str(exposure), str(gain)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f'error={error} ', result.stdout)
        self.assertIn('violations=0 ', result.stdout)
        self.assertIn('cleanup=ok', result.stdout)
        return result.stdout

    def test_endpoints_and_center_use_real_calibration_and_channel_switches(self):
        for e, g in [(0, 0), (120, 3720), (1920, 1920), (2177, 1781), (3840, 5), (4095, 2047)]:
            with self.subTest(exposure=e, gain=g):
                self.assertIn('conversions=5 ', self.run_case(exposure=e, gain=g))
        self.assertIn('us=1000 asa=100 ', self.run_case(exposure=3840, gain=0))
        self.assertIn('us=500000 asa=800 ', self.run_case(exposure=0, gain=3840))

    def test_timeouts_and_bad_inputs_fail_closed_and_clean_up(self):
        for fault, error in [('busy_adc', 1), ('wrong_voltage', 2), ('missing_security', 3),
                             ('supply_timeout', 4), ('ready_timeout', 5), ('calibration_timeout', 5),
                             ('conversion_timeout', 6), ('bad_reference', 7)]:
            with self.subTest(fault=fault):
                self.run_case(fault, error=error)

    def test_driver_rejects_the_previous_enabled_channel_regression(self):
        # Negative control: prove that this test would catch removal of Stop,
        # unlike the original permissive HAL stub. Mutate only a temporary copy.
        source = (HERE / 'capture_controls_adc.c').read_text(encoding='utf-8')
        stop = 'if(HAL_ADC_Stop(a)!=HAL_OK)return 1;'
        self.assertEqual(source.count(stop), 1)
        mutant = self.build_dir / 'missing_stop.c'
        mutant.write_text(source.replace(stop, '/* Deliberately omit Stop for the regression test. */'), encoding='utf-8')
        exe = self.compile(mutant, 'missing-stop')
        self.assertIn('conversions=0 ', self.run_case(error=6, executable=exe))


if __name__ == '__main__':
    unittest.main()
