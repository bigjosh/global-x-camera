"""Offline reviewed-source, frozen-control and recovery-guard checks."""
import importlib.util
import json
from pathlib import Path
import re
import struct
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ready_builder',HERE/'build.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
spec=importlib.util.spec_from_file_location('ready_inspect',HERE/'inspect.py')
inspect=importlib.util.module_from_spec(spec);spec.loader.exec_module(inspect)
BASE=build.ROOT/'tmp/bringup/capture-phy-fast-v36-shutdown-coarse5-20261017'


class StopDwell(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.source=(BASE/'receiver/capture.c').read_text()

    def test_100us_exact_source_control(self):
        self.assertEqual(build.transform_capture(self.source,100),self.source)

    def test_only_threshold_changes_and_stop_state_is_required(self):
        for dwell in (10,0):
            candidate=build.transform_capture(self.source,dwell)
            self.assertEqual(candidate.replace(f'(uint32_t)(DWT->CYCCNT-stable)>={dwell*400}U',
                '(uint32_t)(DWT->CYCCNT-stable)>=40000U'),self.source)
            body=candidate[candidate.index('static void fast_qualify_stop'):candidate.index('\n#if FAST_SHUTDOWN_DATA_OFF')]
            self.assertLess(body.index('if((sr&stop_data)==stop_data)'),body.index('event(409)'))
            self.assertIn('if(HAL_GetTick()-begun>50U) break;',body)
            self.assertIn('attempts<10000000U',body)

    def test_unreviewed_threshold_or_source_rejected(self):
        for dwell in (-1,1,20,101):
            with self.assertRaises(ValueError):build.transform_capture(self.source,dwell)
        with self.assertRaises(ValueError):build.transform_capture(self.source.replace('>=40000U','>=40001U'),10)

    def test_compiled_control_and_guard(self):
        prefix=(BASE/'staged/stage1.bin').read_bytes()
        for dwell in (100,10,0):
            folder=build.ROOT/f'tmp/bringup/capture-phy-ready-v37-streaming-stop{dwell}-coarse5-20261017'
            raw=(folder/'staged/stage1.bin').read_bytes()
            self.assertEqual(raw[:0x830],prefix[:0x830])
            self.assertEqual(build.symbol(folder/'staged','recovery_gpio_park'),0x3418078C)
            for name in ('stage1.c','stage1.S','stage1_sensor.c','recovery_gpio.c','recovery_gpio.h','raw10_memory.c'):
                self.assertEqual((folder/'staged'/name).read_bytes(),(BASE/'staged'/name).read_bytes())
            rm=json.loads((folder/'receiver/manifest.json').read_text())
            self.assertEqual(rm['stop_dwell_us'],dwell)
            self.assertEqual(rm['fast_phy_status_address'],'0x343f8000')
            self.assertEqual(rm['fast_phy_status_words'],544)
            self.assertEqual(rm['shutdown_proof_address'],'0x343f8900')
            self.assertEqual(rm['shutdown_proof_words'],16)
            self.assertTrue(rm['shutdown_data_off'])
            self.assertEqual(rm['coarse_lines'],5)
            if dwell==100:
                for name in ('receiver/capture.bin','staged/stage1.bin','staged/capture_sector_0.bin'):
                    self.assertEqual((folder/name).read_bytes(),(BASE/name).read_bytes())

    def test_no_prefix_or_nor_region_surprises(self):
        original=(BASE/'staged/capture_sector_0.bin').read_bytes()
        for dwell in (100,10,0):
            folder=build.ROOT/f'tmp/bringup/capture-phy-ready-v37-streaming-stop{dwell}-coarse5-20261017'
            pm=json.loads((folder/'staged/manifest.json').read_text())
            sector=(folder/'staged/capture_sector_0.bin').read_bytes()
            self.assertEqual(build.sha(sector),pm['program_sha256'])
            boot=(folder/'staged/stage1_boot.bin').read_bytes()
            receiver=(folder/'receiver/capture.bin').read_bytes()
            self.assertEqual(sector[len(boot):8192],original[len(boot):8192])
            self.assertEqual(sector[8192+len(receiver):],original[8192+len(receiver):])


class AckGate(unittest.TestCase):
    def test_ack_enable_arm_then_existing_streaming_verification(self):
        original=(BASE/'receiver/capture.c').read_text()
        source=build.transform_capture(original,0,'ack')
        main=source[source.index('int main(void)'):]
        steps=['rd8(&sensor,0x0201,&state)','event(425)',
               'fast_streaming_data_enable();','fast_qualify_stop();','arm_receiver();',
               'rd8(&sensor,0x0028,&state)','event(26)','while (!frames)']
        indexes=[main.index(step) for step in steps]
        self.assertEqual(indexes,sorted(indexes))
        for transaction in ('rd8(&sensor,','rd16(&sensor,','rd32(&sensor,','wr8(&sensor,'):
            self.assertEqual(source.count(transaction),original.count(transaction))
        self.assertIn('FAST[6]=READY_GATE;',source)

    def test_frozen_ack_guard_and_diagnostic_identity(self):
        folder=build.ROOT/'tmp/bringup/capture-phy-ready-v38a-ack-stop0-coarse5-20261017'
        self.assertEqual((folder/'staged/stage1.bin').read_bytes()[:0x658],(BASE/'staged/stage1.bin').read_bytes()[:0x658])
        self.assertEqual(build.symbol(folder/'staged','recovery_gpio_park'),0x3418078C)
        manifest=json.loads((folder/'receiver/manifest.json').read_text())
        self.assertEqual(manifest['data_enable'],'ack')
        self.assertEqual(manifest['readiness_gate'],2)
        self.assertEqual(manifest['data_enable_readiness'],'start_ack')
        self.assertIn('-DFAST_DATA_STREAMING=1',manifest['compile_flags'])
        self.assertIn('-DREADY_GATE=2',manifest['compile_flags'])
        self.assertTrue(manifest['shutdown_data_off'])

    def test_decoder_requires_matching_gate_without_losing_raw_words(self):
        manifest=dict(fast_phy_status_address='0x343f8000',fast_phy_status_words=544,
            fast_phy_status_schema=1,fast_phy_record_words=16,fast_phy_header_words=32,
            fast_phy_max_records=32,data_enable='ack',readiness_gate=2)
        words=[0]*544;words[0]=0x46505931;words[6]=2;words[8]=1
        data=struct.pack('<544I',*words)
        self.assertEqual(inspect.decode(data,manifest)['words'],words)
        manifest['readiness_gate']=3
        with self.assertRaises(ValueError):inspect.decode(data,manifest)
        manifest['data_enable']='streaming'
        with self.assertRaises(ValueError):inspect.decode(data,manifest)


class ForceRxGate(unittest.TestCase):
    def test_lane1_pen_delay_zero_is_exact_and_shift_is_bounded(self):
        spec=importlib.util.spec_from_file_location('lane1_pen_builder',HERE/'build_lane1_pen_delay.py')
        delayed=importlib.util.module_from_spec(spec);spec.loader.exec_module(delayed)
        reference=(build.ROOT/'tmp/bringup/capture-phy-ready-v41-force-lane1-stop100-coarse5-20261017/receiver/capture.c').read_text()
        original=(BASE/'receiver/capture.c').read_text()
        self.assertEqual(delayed.transform_capture(original,100,pen_delay_us=0),reference)
        shifted=delayed.transform_capture(original,100,pen_delay_us=200)
        start=shifted.index('  /* Shift digital PHY release only.')
        end=shifted.index('  if(id==405U || id==406U)',start)
        self.assertEqual(shifted[:start]+shifted[end:],reference)
        wait=shifted[start:end]
        self.assertIn('delay_begun)<80000U',wait)
        self.assertIn('delay_attempts<1000000U',wait)
        self.assertIn('fail(0xA7,-1)',wait)
        self.assertNotIn('CSI->',wait)
        self.assertIn('if(TRACE[61]>=1800000U)',shifted)
        with self.assertRaises(ValueError):delayed.transform_capture(original,100,pen_delay_us=100)

    def test_zero_dwell_changes_only_gate_and_declared_proof_dwell(self):
        spec=importlib.util.spec_from_file_location('force_stop0_builder',HERE/'build_force_stop0.py')
        stop0=importlib.util.module_from_spec(spec);spec.loader.exec_module(stop0)
        original=(BASE/'receiver/capture.c').read_text()
        reference=build.transform_capture(original,100,'force_stop')
        self.assertEqual(stop0.transform_capture(original,100,'force_stop'),reference)
        candidate=stop0.transform_capture(original,0,'force_stop')
        self.assertEqual(candidate,reference.replace('DWT->CYCCNT-stable)>=40000U','DWT->CYCCNT-stable)>=0U')
                         .replace('FORCE[28]=40000U;','FORCE[28]=0U;'))
        self.assertIn('if((sr&stop_data)==stop_data)',candidate)
        w,manifest,fast=self.proof_fixture()
        w[28]=0
        self.assertFalse(inspect.decode_force(struct.pack('<32I',*w),manifest,fast)['completed'])
        manifest['stop_dwell_cycles']=0
        self.assertTrue(inspect.decode_force(struct.pack('<32I',*w),manifest,fast)['completed'])
        w[20]=0
        self.assertFalse(inspect.decode_force(struct.pack('<32I',*w),manifest,fast)['completed'])

    def test_lane1_only_transform_is_narrow_and_does_not_hide_mode5(self):
        import force_rx_lane1
        original=(BASE/'receiver/capture.c').read_text()
        both=build.force_rx.capture(original)
        lane1=force_rx_lane1.capture(original)
        self.assertEqual(lane1,both.replace('(READY_GATE==5U?3U:0U)','2U')
                         .replace('(READY_GATE==5U?force:0U)','CSI_PMCR_FRXMDL1'))
        hal=(BASE/'receiver/hal_dcmipp.c').read_text()
        lane1_hal=force_rx_lane1.hal(hal,True)
        self.assertIn('WRITE_REG(csi_instance->PMCR,CSI_PMCR_FRXMDL1);',lane1_hal)
        for token in ('FCR','IER','PRCR','PCR'):
            self.assertEqual(lane1_hal.count(token),hal.count(token))
        w,manifest,fast=self.proof_fixture()
        for index in (13,16,19):w[index]=2
        self.assertFalse(inspect.decode_force(struct.pack('<32I',*w),manifest,fast)['completed'])
        w[2]=6;manifest.update(data_enable='force_lane1',readiness_gate=6);fast['header'][6]=6
        self.assertTrue(inspect.decode_force(struct.pack('<32I',*w),manifest,fast)['completed'])

    def test_frozen_pair_guard_and_proof_layout(self):
        prefix=(BASE/'staged/stage1.bin').read_bytes()
        original=(BASE/'staged/capture_sector_0.bin').read_bytes()
        for name,mode in [('early',4),('force',5)]:
            folder=build.ROOT/f'tmp/bringup/capture-phy-ready-v39-{name}-stop100-coarse5-20261017'
            self.assertEqual((folder/'staged/stage1.bin').read_bytes()[:0x658],prefix[:0x658])
            self.assertEqual(build.symbol(folder/'staged','recovery_gpio_park'),0x3418078C)
            for source in ('stage1.c','stage1.S','stage1_sensor.c','recovery_gpio.c','recovery_gpio.h','raw10_memory.c'):
                self.assertEqual((folder/'staged'/source).read_bytes(),(BASE/'staged'/source).read_bytes())
            rm=json.loads((folder/'receiver/manifest.json').read_text())
            pm=json.loads((folder/'staged/manifest.json').read_text())
            self.assertEqual(rm['readiness_gate'],mode)
            self.assertEqual(rm['force_rx_proof_address'],'0x343f8940')
            self.assertEqual(rm['force_rx_proof_words'],32)
            self.assertEqual(rm['force_rx_proof_schema'],1)
            self.assertTrue(rm['shutdown_data_off'])
            self.assertIn('-DFAST_DATA_STREAMING=0',rm['compile_flags'])
            sector=(folder/'staged/capture_sector_0.bin').read_bytes()
            boot=(folder/'staged/stage1_boot.bin').read_bytes()
            receiver=(folder/'receiver/capture.bin').read_bytes()
            self.assertEqual(build.sha(sector),pm['program_sha256'])
            self.assertEqual(build.sha(receiver),rm['raw_sha256'])
            self.assertEqual(sector[len(boot):8192],original[len(boot):8192])
            self.assertEqual(sector[8192+len(receiver):],original[8192+len(receiver):])
            self.assertEqual((folder/'receiver/capture.c').read_text(),
                             build.transform_capture((BASE/'receiver/capture.c').read_text(),100,rm['data_enable']))

    def test_both_controls_have_same_capture_source_and_bounded_gate_before_polls(self):
        original=(BASE/'receiver/capture.c').read_text()
        early=build.transform_capture(original,100,'early_stop')
        force=build.transform_capture(original,100,'force_stop')
        self.assertEqual(early,force)
        main=force[force.index('int main(void)'):]
        steps=['prepare_receiver();','fast_streaming_data_enable();',
               'ready_force_before_stop();','fast_qualify_stop();','ready_force_release();',
               'arm_receiver();','rd8(&sensor,0x0201,&state)','rd8(&sensor,0x0028,&state)',
               'while (!frames)']
        positions=[main.index(step) for step in steps]
        self.assertEqual(positions,sorted(positions))
        for transaction in ('rd8(&sensor,','rd16(&sensor,','rd32(&sensor,','wr8(&sensor,'):
            self.assertEqual(force.count(transaction),original.count(transaction))
        self.assertIn('ready_force_guard();\n    uint32_t sr=CSI->SR1',force)
        self.assertIn('if((sr&stop_data)==stop_data)',force)
        self.assertIn('(uint32_t)(DWT->CYCCNT-stable)>=40000U',force)
        self.assertIn('if(HAL_GetTick()-begun>50U) break;',force)
        self.assertIn('if(at!=6U) ready_force_stop_seen',force)
        self.assertIn('CLEAR_BIT(CSI->PMCR,force); __DSB();',force)
        self.assertIn('WRITE_REG(CSI->PMCR,CSI_PMCR_FRXMDL0|CSI_PMCR_FRXMDL1);',force)
        for token in ('CSI->FCR','CSI->IER'):
            self.assertEqual(force.count(token),original.count(token))
        for mode in ('early_stop','force_stop'):
            with self.assertRaises(ValueError):build.transform_capture(original,0,mode)

    def test_force_hal_only_omits_final_force_clear(self):
        original=(BASE/'receiver/hal_dcmipp.c').read_text()
        self.assertEqual(build.force_rx.hal(original,False),original)
        force=build.force_rx.hal(original,True)
        self.assertEqual(force.count('CLEAR_REG(csi_instance->PMCR)'),0)
        self.assertEqual(force.count('fast_phy_hook(406)'),1)
        for token in ('FCR','IER','PRCR','PCR'):
            self.assertEqual(force.count(token),original.count(token))

    def proof_fixture(self):
        manifest=dict(force_rx_proof_address='0x343f8940',force_rx_proof_words=32,
            force_rx_proof_schema=1,data_enable='force_stop',readiness_gate=5,stop_dwell_cycles=40000)
        w=[0]*32;w[:6]=[0x52465231,1,5,6,100,200]
        for at,cycle,pmcr in [(6,400,0x11003),(9,600,3),(12,800,3),
                              (15,41100,3),(18,41200,3),(21,41300,0)]:
            w[at:at+3]=[cycle,pmcr,0x02080000 if at>=12 else 0]
        w[24:32]=[900,900,900,1000,40000,0,3,0x344]
        fast=dict(header=[0]*32,overflow=0,records=[dict(event=e,cycles=c) for e,c in
            [(399,300),(405,500),(406,700),(409,41050),(441,41400),(422,41500),(425,41600),(426,41700)]])
        fast['header'][6]=5
        return w,manifest,fast

    def test_force_proof_requires_current_sequence_and_current_stop_state(self):
        w,manifest,fast=self.proof_fixture()
        result=inspect.decode_force(struct.pack('<32I',*w),manifest,fast)
        self.assertTrue(result['completed']);self.assertEqual(result['words'],w)
        self.assertFalse(inspect.decode_force(struct.pack('<32I',*w),manifest)['completed'])
        for index,value in ((20,0),(17,0),(31,0),(30,0),(29,0xFFFFFFFF),(28,0)):
            bad=w.copy();bad[index]=value
            self.assertFalse(inspect.decode_force(struct.pack('<32I',*bad),manifest,fast)['completed'])
        stale=w.copy();stale[5]=9999999
        self.assertFalse(inspect.decode_force(struct.pack('<32I',*stale),manifest,fast)['completed'])
        before_pen=w.copy();before_pen[24]=500
        self.assertFalse(inspect.decode_force(struct.pack('<32I',*before_pen),manifest,fast)['completed'])
        wrong=dict(manifest,force_rx_proof_address='0x343f8944')
        with self.assertRaises(ValueError):inspect.decode_force(struct.pack('<32I',*w),wrong,fast)


if __name__=='__main__':unittest.main()
