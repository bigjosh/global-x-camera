"""Explicit SD frequencies bind build, terminal, card and width proof."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from test_bench import bench, proof
from test_sd_width import FakeRead

HERE=Path(__file__).resolve().parent


class ClockGuards(unittest.TestCase):
    def manifest(self,hz):
        return dict(sd_clock_hz=hz,flags=[f'-DRAW_SD_CLOCK_HZ={hz}U'])

    def test_legacy_default_and_explicit_frequencies(self):
        self.assertEqual(bench.clock_layout({}),25000000)
        for hz in (12500000,25000000):
            self.assertEqual(bench.clock_layout(self.manifest(hz)),hz)

    def test_clock_or_compiler_identity_mismatch_rejected(self):
        bad=[dict(sd_clock_hz=x) for x in (True,'12500000',100000,0,50000000)]
        bad.extend([dict(sd_clock_hz=12500000,flags=[]),
                    dict(sd_clock_hz=12500000,flags=['-DRAW_SD_CLOCK_HZ=25000000U']),
                    dict(flags=['-DRAW_SD_CLOCK_HZ=12500000U']),
                    dict(sd_clock_hz=25000000,flags=['-DRAW_SD_CLOCK_HZ=25000000U']*2)])
        for m in bad:
            with self.subTest(manifest=m),self.assertRaises(ValueError):
                bench.clock_layout(m)

    def test_width_proof_requires_correct_divider_and_hwfc(self):
        for hz,clkcr in ((12500000,0x24006),(25000000,0x24003)):
            m=self.manifest(hz)
            m.update(sd_bus_width=4,sd_width_proof=0x34308000,sd_width_proof_bytes=24,
                     bss_start=0x34307000,bss_end=0x34309000)
            m['flags'].append('-DSD_BUS_WIDTH=4')
            good=[4,5,0x920,1,clkcr,4]
            self.assertEqual(bench.width_snapshot(FakeRead(good),m,'ok')['configured_clkcr'],clkcr)
            for bad in (0x4003,0x24003 if hz==12500000 else 0x24006,clkcr|0x40000):
                words=good.copy();words[4]=bad
                with self.subTest(hz=hz,clkcr=bad),self.assertRaises(ValueError):
                    bench.width_snapshot(FakeRead(words),m,'bad')

    def test_terminal_clock_must_match_requested_build(self):
        for operation in (1,2,3):
            p,m,q=proof(operation);m.update(self.manifest(12500000))
            with self.assertRaises(ValueError):bench.validate(p,m,q)
            p['clock_hz']=12500000
            bench.validate(p,m,q)
            p['clock_hz']=100000
            with self.assertRaises(ValueError):bench.validate(p,m,q)

    def test_live_card_clock_must_match_terminal_and_build(self):
        names=('sector_count read_sectors written_sectors read_cycles write_cycles ready_cycles '
            'initialized controller_owned media_idle clock_hz ocr rca cid0 cid1 cid2 cid3 '
            'csd0 csd1 csd2 csd3 error error_stage error_command error_sta stage last_command '
            'last_argument last_sta last_r1 command_count last_ready_r1 last_stop_r1 cleanup_error '
            'transfer_words transfer_sta transfer_cycles init_cycles gpioc_idr gpioe_idr '
            'vddio5_control saved_sdmmc_mux saved_demcr saved_dwt timer_owned').split()
        card={name:0 for name in names}
        card.update(sector_count=8+3*3731,read_sectors=3,written_sectors=3732,
                    media_idle=1,stage=9,last_ready_r1=0x900,clock_hz=12500000)
        class Reader:
            def upload(self,address,size,name):
                if size!=200:raise AssertionError('Unexpected read')
                return struct.pack('<6Q38I',*(card[n] for n in names))
        p,m,q=proof(1);m.update(self.manifest(12500000));p['clock_hz']=12500000
        bench.card_snapshot(Reader(),m,p,'ok')
        for card_hz,proof_hz in ((25000000,12500000),(12500000,25000000),(25000000,25000000)):
            card['clock_hz']=card_hz;p['clock_hz']=proof_hz
            with self.subTest(card_hz=card_hz,proof_hz=proof_hz),self.assertRaises(ValueError):
                bench.card_snapshot(Reader(),m,p,'bad')

    def test_explicit_fallback_clock_is_valid_for_flash_standby(self):
        for flash,standby in ((False,False),(True,False),(True,True)):
            m=self.manifest(12500000);m.update(flash=flash,standby=standby)
            self.assertEqual(bench.clock_layout(m),12500000)
            m['flags']=[]
            with self.assertRaises(ValueError):bench.clock_layout(m)

    def test_clock_promotion_does_not_promote_slew_or_compensation(self):
        with tempfile.TemporaryDirectory(prefix='sd-clock-options-') as root:
            out=Path(root)/'never-created'
            for options,message in [(('--sd-gpio-speed','0'),'Nondefault SD GPIO speed'),
                                    (('--sd-fixed-compensation',),'Fixed compensation')]:
                run=subprocess.run([sys.executable,str(HERE/'build.py'),'--out',str(out),
                                    '--sd-clock-hz','12500000','--flash','--standby',*options],capture_output=True,text=True)
                self.assertEqual(run.returncode,2)
                self.assertIn(message,run.stderr)
                self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
