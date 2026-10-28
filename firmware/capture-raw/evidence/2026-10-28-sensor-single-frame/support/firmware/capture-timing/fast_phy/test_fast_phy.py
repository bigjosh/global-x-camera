"""Offline sequencing, frozen-guard and diagnostic-boundary regression checks."""
import importlib.util
import json
from pathlib import Path
import re
import struct
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('fast_builder',HERE/'build.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
spec=importlib.util.spec_from_file_location('fast_inspect',HERE/'inspect.py')
inspect=importlib.util.module_from_spec(spec);spec.loader.exec_module(inspect)
BASE=build.ROOT/'tmp/bringup/capture-recovery-pe1-v34c-20261017'


class Sequencing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.text=build.transform_capture((BASE/'receiver/capture.c').read_text())

    def test_configuration_budget_then_ready_enable_stop_arm(self):
        t=self.text[self.text.index('int main(void)'):]
        markers=['  prepare_receiver();','  if(TRACE[61]>=1800000U)',
                 'rd8(&sensor,0x0201,&state)','event(425)',
                 'rd8(&sensor,0x0028,&state)','event(26)',
                 '  fast_streaming_data_enable();','  fast_qualify_stop();',
                 '  if(frames || vsyncs)','  arm_receiver();']
        positions=[t.index(x) for x in markers]
        self.assertEqual(positions,sorted(positions))

    def test_prepare_does_not_arm_and_no_new_i2c_transactions(self):
        t=self.text
        prepare=t[t.index('static void prepare_receiver'):t.index('static void arm_receiver')]
        self.assertNotIn('HAL_DCMIPP_CSI_PIPE_Start',prepare)
        base=(BASE/'receiver/capture.c').read_text()
        for operation in ('rd8(&sensor,','rd16(&sensor,','rd32(&sensor,','wr8(&sensor,'):
            self.assertEqual(t.count(operation),base.count(operation))
        self.assertNotIn('wr8(&sensor,0x0202,2)',t)

    def test_raw_interrupt_before_hal_and_pipe_stop_boundary(self):
        irq=self.text[self.text.index('void CSI_IRQHandler'):self.text.index('void EXTI0_IRQHandler')]
        self.assertLess(irq.index('fast_snapshot(420)'),irq.index('HAL_DCMIPP_CSI_IRQHandler'))
        self.assertLess(self.text.index('fast_snapshot(439)'),self.text.index('VD6G_Stop(&sensor)'))
        self.assertGreater(self.text.index('fast_snapshot(439)'),self.text.index('  check(32, HAL_DCMIPP_CSI_PIPE_Stop'))

    def test_bounded_records_and_peripheral_clock_guards(self):
        t=(HERE/'receiver_helpers.inc').read_text()
        for guard in ('RCC_APB5RSTR_CSIRST','RCC_APB5ENR_CSIEN','RCC_DIVENR_IC18EN'):
            self.assertLess(t.index(guard),t.index('r[3]=CSI->SR0'))
        self.assertIn('n<FAST_MAX_RECORDS',t)
        self.assertIn('HAL_GetTick()-begun>50U',t)
        self.assertIn('attempts<10000000U',t)

    def test_guard_sources_and_executable_region_unchanged(self):
        base_raw=(BASE/'staged/stage1.bin').read_bytes()
        # Through0x34180A58 includes entry, park, complete recovery path and
        # its literal pool. First changed byte is later at0x34180C30.
        for mode in ('early','streaming'):
            folder=build.ROOT/f'tmp/bringup/capture-phy-fast-v35-{mode}-20261017'
            for name in ('stage1.c','stage1.S','recovery_gpio.c','recovery_gpio.h','stage1_sensor.c'):
                self.assertEqual((BASE/'staged'/name).read_bytes(),(folder/'staged'/name).read_bytes())
            raw=(folder/'staged/stage1.bin').read_bytes()
            self.assertEqual(raw[:0x658],base_raw[:0x658])
            self.assertEqual(len(raw),len(base_raw))


class CoarseExposure(unittest.TestCase):
    def setUp(self):self.source=(BASE/'staged/stage1_sensor.c').read_text()

    def manual(self,text):
        values=re.search(r'manual\[12\]=\{([^}]+)\}',text)[1]
        return bytes(int(value,0) for value in values.split(','))

    def test_default_is_byte_identical(self):
        self.assertEqual(build.transform_sensor(self.source,1428),self.source)

    def test_only_exposure_array_bytes_change(self):
        baseline=self.manual(self.source)
        for coarse in (5,21,40,256,65535):
            text=build.transform_sensor(self.source,coarse)
            manual=self.manual(text)
            self.assertEqual(manual[:2]+manual[4:],baseline[:2]+baseline[4:])
            self.assertEqual(int.from_bytes(manual[2:4],'little'),coarse)
            # Outside the one manual array declaration, source is unchanged.
            strip=lambda s:re.sub(r'static const uint8_t manual\[12\].*', '',s)
            self.assertEqual(strip(text),strip(self.source))

    def test_out_of_range_and_changed_source_rejected(self):
        for coarse in (0,4,65536,-1):
            with self.assertRaises(build.argparse.ArgumentTypeError):build.transform_sensor(self.source,coarse)
        with self.assertRaises(ValueError):build.transform_sensor(self.source.replace('0x94,5','0x95,5'),5)

    def test_compiled_short_variants_change_only_manual_exposure_bytes(self):
        first=build.ROOT/'tmp/bringup/capture-phy-fast-v35-streaming-20261017'
        prefix=(first/'staged/stage1.bin').read_bytes()
        receiver=(first/'receiver/capture.bin').read_bytes()
        match=re.search(r'^([0-9a-fA-F]+) [Tt] manual\.\d+$',(first/'staged/symbols.txt').read_text(),re.M)
        self.assertIsNotNone(match)
        manual=int(match[1],16)-0x34180400
        for coarse in (5,21,40):
            folder=build.ROOT/f'tmp/bringup/capture-phy-fast-v35-streaming-coarse{coarse}-20261017'
            raw=(folder/'staged/stage1.bin').read_bytes()
            self.assertEqual(len(raw),len(prefix))
            self.assertEqual([i for i,(a,b) in enumerate(zip(raw,prefix)) if a!=b],[manual+2,manual+3])
            self.assertEqual(int.from_bytes(raw[manual+2:manual+4],'little'),coarse)
            self.assertEqual((folder/'receiver/capture.bin').read_bytes(),receiver)
            for sub in ('staged','receiver'):
                manifest=json.loads((folder/sub/'manifest.json').read_text())
                self.assertEqual(manifest['coarse_lines'],coarse)


class Decode(unittest.TestCase):
    def setUp(self):
        self.manifest=dict(fast_phy_status_address='0x343f8000',fast_phy_status_words=544,
            fast_phy_status_schema=1,fast_phy_record_words=16,fast_phy_header_words=32,
            fast_phy_max_records=32,data_enable='streaming')
        self.words=[0]*544;self.words[0]=0x46505931;self.words[6]=self.words[8]=1

    def run_decode(self):return inspect.decode(struct.pack('<544I',*self.words),self.manifest)

    def test_stale_records_beyond_count_ignored(self):
        self.words[32]=430;self.words[47]=1
        self.assertEqual(self.run_decode()['records'],[])
        self.assertFalse(self.run_decode()['first_physical_exposure_ordinal_supported'])

    def test_requires_first_strobe_ordinal_at_vsync_and_frame(self):
        self.words[2]=2;self.words[30]=self.words[31]=1
        self.words[32]=429;self.words[46]=self.words[47]=1
        self.words[48]=430;self.words[61]=self.words[63]=1
        self.assertTrue(self.run_decode()['first_physical_exposure_ordinal_supported'])
        self.words[63]=2
        self.assertFalse(self.run_decode()['first_physical_exposure_ordinal_supported'])

    def test_rejects_wrong_layout_count_mode(self):
        self.manifest['fast_phy_status_address']='0x34000000'
        with self.assertRaises(ValueError):self.run_decode()
        self.manifest['fast_phy_status_address']='0x343f8000';self.words[2]=33
        with self.assertRaises(ValueError):self.run_decode()
        self.words[2]=0;self.words[6]=0
        with self.assertRaises(ValueError):self.run_decode()


class Shutdown(unittest.TestCase):
    def setUp(self):
        self.manifest=dict(shutdown_data_off=True,shutdown_proof_address='0x343f8900',
                           shutdown_proof_words=16,shutdown_proof_schema=1)
        self.words=[0]*16
        self.words[:6]=[0x46534431,1,4,0x44,0x30000,0]
        self.words[10:13]=[2,15,3]

    def run_decode(self):return inspect.decode_shutdown(struct.pack('<16I',*self.words),self.manifest)

    def test_rejects_each_active_bit_and_bad_clock_reset(self):
        self.assertTrue(self.run_decode()['proof_complete'])
        for word,mask in ((6,0x20000),(7,8),(8,0x8000),(9,0x80000000),(5,0x44)):
            self.words[word]|=mask
            self.assertFalse(self.run_decode()['proof_complete'])
            self.words[word]&=~mask
        self.words[3]=4
        self.assertFalse(self.run_decode()['proof_complete'])
        self.words[3]=0x44;self.words[4]=0x10000
        self.assertFalse(self.run_decode()['proof_complete'])

    def test_standalone_or_stale_proof_not_current_completion(self):
        self.assertTrue(self.run_decode()['proof_complete'])
        self.assertFalse(self.run_decode()['completed'])
        self.words[13:15]=[125,130]
        fast={'overflow':0,'header':[0,40],
              'records':[{'event':event,'cycles':cycle} for event,cycle in
                         ((439,100),(442,120),(443,140),(436,160))]}
        data=struct.pack('<16I',*self.words)
        self.assertTrue(inspect.decode_shutdown(data,self.manifest,fast)['completed'])
        fast['records'][1]['cycles']=135
        self.assertFalse(inspect.decode_shutdown(data,self.manifest,fast)['completed'])

    def test_skipped_reads_not_reported_idle(self):
        self.words[2]=1;self.words[15]=0xFFFFFFFF
        result=self.run_decode()
        self.assertEqual(result['result'],-1)
        self.assertFalse(result['peripheral_reads_performed'])
        self.assertTrue(all(v is None for v in result['idle'].values()))
        self.assertFalse(result['completed'])

    def test_wrong_layout_rejected(self):
        self.manifest['shutdown_proof_address']='0x343f8000'
        with self.assertRaises(ValueError):self.run_decode()

    def test_post_stop_order_no_flag_writes(self):
        source=build.transform_capture((BASE/'receiver/capture.c').read_text())
        main=source[source.index('int main(void)'):]
        markers=['check(32, HAL_DCMIPP_CSI_PIPE_Stop','fast_snapshot(439)',
                 'fast_shutdown_data_off();','check(33, VD6G_Stop','fast_snapshot(436)']
        positions=[main.index(m) for m in markers]
        self.assertEqual(positions,sorted(positions))
        helper=(HERE/'receiver_helpers.inc').read_text()
        helper=helper[helper.index('static void fast_shutdown_data_off'):helper.index('\n#endif',helper.index('static void fast_shutdown_data_off'))]
        self.assertLess(helper.index('SHUTDOWN[5]&resets'),helper.index('SHUTDOWN[6]=CSI->SR0'))
        self.assertLess(helper.index('SHUTDOWN[9]&DCMIPP_P0FSCR_PIPEN'),helper.index('CLEAR_BIT(CSI->PCR'))
        self.assertIn('CLEAR_BIT(CSI->PCR,CSI_PCR_DL0EN|CSI_PCR_DL1EN)',helper)
        self.assertNotIn('CSI->FCR',helper)
        self.assertNotIn('CSI->IER',helper)

    def test_compiled_default_off_exact_and_v36_guard_preserved(self):
        first=build.ROOT/'tmp/bringup/capture-phy-fast-v35-streaming-20261017'
        off=build.ROOT/'tmp/bringup/capture-phy-fast-v36-default-off-check-20261017'
        for name in ('receiver/capture.bin','staged/stage1.bin','staged/capture_sector_0.bin'):
            self.assertEqual((first/name).read_bytes(),(off/name).read_bytes())
        base_raw=(BASE/'staged/stage1.bin').read_bytes()
        for suffix in ('shutdown','shutdown-coarse5'):
            folder=build.ROOT/f'tmp/bringup/capture-phy-fast-v36-{suffix}-20261017'
            self.assertEqual((folder/'staged/stage1.bin').read_bytes()[:0x658],base_raw[:0x658])
            for name in ('stage1.c','stage1.S','recovery_gpio.c','recovery_gpio.h'):
                self.assertEqual((folder/'staged'/name).read_bytes(),(BASE/'staged'/name).read_bytes())


if __name__=='__main__':unittest.main()
