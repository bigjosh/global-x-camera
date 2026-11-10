"""Offline HOLD admission checks; no instrument access or recovery permission."""
import copy
import json
import unittest
from pathlib import Path
from test_bench import bench
from gpio_hold_transform import contract


HERE=Path(__file__).resolve().parent
NORMAL=HERE/'evidence/2026-10-28-sensor-single-frame/flash-standby-v1/manifest.json'


class GPIOHoldAdmission(unittest.TestCase):
    def setUp(self):
        self.legacy=json.loads(NORMAL.read_text())
        self.m=copy.deepcopy(self.legacy)
        # Structural selection is separate from the packaged binary audit.
        self.m.update(gpio_hold=True,gpio_hold_contract=contract(True))
        self.m['flags'].append('-DRAW_GPIO_HOLD=1')

    def test_frozen_normal_manifest_is_unchanged_and_disabled_is_noop(self):
        self.assertFalse(bench.gpio_hold_layout(self.legacy,1))
        self.assertFalse(bench.gpio_hold_layout({}))
        self.assertFalse(bench.gpio_hold_layout({'gpio_hold':False}))
        self.assertNotIn('gpio_hold',json.loads(NORMAL.read_text()))

    def test_exact_historical_hold_packages_remain_inspectable(self):
        for name in ('hold-standby','hold-awake'):
            archived=HERE/'evidence/2026-11-07-gpio-hold'/name/'manifest.json'
            with self.subTest(name=name):
                self.assertTrue(bench.gpio_hold_layout(json.loads(archived.read_text())))

    def test_awake_and_standby_only_admit_explicit_bound_flash_selection(self):
        for standby in (False,True):
            m=copy.deepcopy(self.m);m['standby']=standby;m['gpio_hold_contract']=contract(standby)
            m['flags']=[f.replace('-DRAW_STANDBY=1',f'-DRAW_STANDBY={int(standby)}') for f in m['flags']]
            for operation in (None,1,3):
                with self.subTest(standby=standby,operation=operation):
                    self.assertTrue(bench.gpio_hold_layout(m,operation))
        with self.assertRaises(ValueError):bench.gpio_hold_layout(self.m,2)

    def test_hidden_or_partial_hold_selection_is_rejected(self):
        for m in ({'gpio_hold':1},{'gpio_hold':'true'},
                {'flags':['-DRAW_GPIO_HOLD=1']},{'flags':['-DRAW_GPIO_HOLD=0']},
                {'flags':['-DRAW_GPIO_HOLD']},
                {'gpio_hold_contract':{}},{'gpio_hold':False,'gpio_hold_contract':None}):
            with self.subTest(manifest=m),self.assertRaises(ValueError):bench.gpio_hold_layout(m)
        for contract in (None,{},[],True,'PD7'):
            m=copy.deepcopy(self.m);m['gpio_hold_contract']=contract
            with self.subTest(contract=contract),self.assertRaises(ValueError):bench.gpio_hold_layout(m)

    def test_diagnostics_ram_and_non_normal_profiles_are_not_promoted(self):
        changes=(dict(flash=False),dict(standby=1),dict(sensor_single_frame=False),
            dict(sensor_autostop=False),dict(board_eth_powerdown=False),dict(error_blinks=False),
            dict(sd_clock_hz=12500000),dict(sd_bus_width=1),dict(sd_clk_gpio_speed=2),
            dict(sd_gpio_speed=2),dict(transport='pio'),dict(pattern=1),dict(exposure_coarse=30000),
            dict(chunk_sectors=128),dict(magic_layout_version=1),dict(dma_sleep=True),
            dict(dma_sleep_profile=True),dict(dma_sleep_probe=True),dict(power_probe='cpu'),
            dict(sd_init_gap_ms=200),dict(cycle_trace={'schema':1}),dict(sd_idma_read=True),
            dict(sd_read_diagnostics=True),dict(error_test_code=4),dict(error_after_frame_test=True),
            dict(raw_dma_tail_wait=True),dict(sd_early_run_clock=True),dict(sd_fixed_compensation=True))
        for change in changes:
            m=copy.deepcopy(self.m);m.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):bench.gpio_hold_layout(m,1)

    def test_flags_cannot_contradict_the_selected_profile_or_be_duplicated(self):
        keys=('RAW_GPIO_HOLD','RAW_FLASH','RAW_STANDBY','RAW_SENSOR_AUTOSTOP',
            'RAW_SENSOR_SINGLE_FRAME','RAW_BOARD_ETH_POWERDOWN','RAW_ERROR_PREFIX',
            'SD_REVIEW_PROFILE','SD_STARTUP_OPT','SD_BUS_WIDTH','RAW_SD_CLOCK_HZ',
            'SD_GPIO_SPEED','SD_CLOCK_NEGEDGE','SD_CLOCK_NEGEDGE_INIT','RAW_MAGIC_FORMAT',
            'RAW_LINE_STREAM','RAW_ASYNC_STOP','RAW_DMA','RAW_PREINIT','RAW_LINE_SNAPSHOTS',
            'RAW_LINE_POISON','RAW_WHOLE_IMAGE_PREERASE','RAW_DMA_SLEEP','RAW_DMA_TAIL_WAIT',
            'SD_EARLY_RUN_CLOCK','SD_IDMA_READ','SD_FIXED_COMPENSATION','SD_HIGH_SPEED',
            'SD_HIGH_SPEED_MIXED_SLEW','SD_HIGH_SPEED_FIXED_COMPENSATION',
            'SD_HIGH_SPEED_COMBINED_ELECTRICAL','RAW_PATTERN','RAW_EXPOSURE_COARSE',
            'RAW_CHUNK_SECTORS','STAGE1_SENSOR_TRIM','LOW_POWER_MODE','LOW_POWER_ENTRY_DELAY_US')
        for key in keys:
            flag=next(f for f in self.m['flags'] if f.startswith('-D'+key+'='))
            for mutation in ('missing','duplicate','contradictory'):
                m=copy.deepcopy(self.m)
                if mutation=='missing':m['flags'].remove(flag)
                elif mutation=='duplicate':m['flags'].append(flag)
                else:m['flags'][m['flags'].index(flag)]='-D'+key+'=99'
                with self.subTest(key=key,mutation=mutation),self.assertRaises(ValueError):
                    bench.gpio_hold_layout(m,1)

    def test_hidden_diagnostic_compiler_selection_is_rejected(self):
        for key in ('SD_DMA_SLEEP_PROFILE','RAW_DMA_SLEEP_PROBE','RAW_CYCLE_TRACE',
                'SD_CLK_GPIO_SPEED','SD_READ_DIAGNOSTICS','RAW_POWER_PROBE','RAW_SD_INIT_GAP_MS'):
            m=copy.deepcopy(self.m);m['flags'].append('-D'+key+'=1')
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'diagnostic compiler'):
                bench.gpio_hold_layout(m,1)

    def test_common_admission_rejects_hidden_hold_before_other_profile_work(self):
        m=copy.deepcopy(self.legacy);m['flags'].append('-DRAW_GPIO_HOLD=1')
        with self.assertRaisesRegex(ValueError,'Unexpected GPIO HOLD'):
            bench.diagnostic_layout(m,1)

    def test_pin_release_and_recovery_policies_cannot_be_changed_by_metadata(self):
        for key,value in self.m['gpio_hold_contract'].items():
            m=copy.deepcopy(self.m)
            m['gpio_hold_contract'][key]=not value if type(value) is bool else None
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'contract differs'):
                bench.gpio_hold_layout(m)


if __name__=='__main__':unittest.main()
