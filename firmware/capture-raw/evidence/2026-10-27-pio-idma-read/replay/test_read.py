"""Offline runner/reference/failure tests: no instrument or real subprocess."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('read_runner_test',HERE/'run_read.py')
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf-8')


class ReadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='read-runner-offline-')
        self.root=Path(self.temp.name)
        self.args=SimpleNamespace(build=self.root/'build',out=self.root/'out',mode='pio',pair=1,clock_hz=25000000,
            prior=None,recovery_build=self.root/'installed',reference_proof=self.root/'reference/verified.json',
            execute=True)
        self.manifest=dict(binary_sha256='test',sd_idma_read=False,sd_clock_hz=25000000)
        self.header=b'GXRS'+bytes(index%256 for index in range(508))
        self.identity=dict(sector_count=122507264,cid0=83,cid1=1146433824,cid2=269787418,cid3=1979815748)
        self.reference=dict(card_identity=self.identity)

    def tearDown(self):
        self.temp.cleanup()

    def mocked_admission(self):
        return self.manifest,SimpleNamespace(),self.header,self.reference

    def test_plan_never_runs_hardware(self):
        self.args.execute=False
        with patch.object(runner,'admission',return_value=self.mocked_admission()), \
                patch.object(runner.subprocess,'run') as command,contextlib.redirect_stdout(io.StringIO()):
            plan=runner.run(self.args)
        command.assert_not_called()
        self.assertFalse(self.args.out.exists())
        self.assertEqual((plan['lba'],plan['count']),(0,1))
        self.assertFalse(plan['automatic_retry'])

    def test_existing_attempt_rejected(self):
        self.args.out.mkdir()
        with self.assertRaisesRegex(ValueError,'existing attempt'):
            runner.admission(self.args)

    def test_compare_checks_all512_bytes(self):
        observed=bytearray(self.header)
        observed[511]^=1
        result=runner.compare_bytes(observed,self.header)
        self.assertFalse(result['bytes_equal'])
        self.assertEqual(result['first_difference'],511)
        self.assertEqual(result['matching_words'],127)

    def test_partial_buffer_is_not_full_comparison(self):
        with self.assertRaisesRegex(ValueError,'complete512'):
            runner.compare_bytes(self.header[:-1],self.header)

    def test_historical_reference_verifies_entire_source_not_just_header(self):
        data=self.header+bytes(512)
        proof=dict(passed=True,proof=dict(operation=3,result=0,read_lba=0,read_count=2),
            card=self.identity,read_sha256=hashlib.sha256(data).hexdigest())
        write(self.args.reference_proof,proof)
        path=self.args.reference_proof.parent/'sectors.bin'
        path.write_bytes(data)
        header,meta=runner.reference_data(self.args.reference_proof)
        self.assertEqual(header,self.header)
        self.assertTrue(meta['full_payload_hash_verified'])
        path.write_bytes(self.header+bytes(511)+b'1')
        with self.assertRaisesRegex(ValueError,'hash-matching'):
            runner.reference_data(self.args.reference_proof)

    def prepare_failed_read(self):
        write(self.args.out/'read/proof.json',dict(operation=3,nonce=123,result=1038,stage=4,sd_error=14,
            cleanup_error=10,read_lba=0,read_count=1,arm=0,camera_ready=0,frames=0,
            card_write_hi=0,card_write_lo=0))
        write(self.args.out/'read/read-diagnostics.json',dict(
            diagnostics=dict(magic=0x31445253,version=1,mode=0,lba=0,count=1,
                destination=0x34200000,requested_bytes=512,clkcr=0x34003,captured=1,result=14),
            card=dict(**self.identity,written_sectors=0,clock_hz=25000000),
            camera=dict(magic=0x31504352,version=1,phase=2,held=1,moder=0x400,odr=0,idr=0,
                otyper=0,pupdr=0,sd_gpio_readable=1,c_ospeed=0xFF3,e_ospeed=0x300,
                checked=50000,assert_begin=100),
            attribution=dict(binary_sha256='test',nonce=123,hardware_mutations=False,
                idle_permission=False,immutable_code_equal=True,final_proof_equal=True,
                expected_immutable_sha256='same',observed_immutable_sha256='same',cfsr=0,hfsr=0),
            nonce=123,operation_result=1038,buffer_bytes=512,
            buffer_sha256=hashlib.sha256(self.header).hexdigest()))
        (self.args.out/'read/read-buffer.bin').write_bytes(self.header)

    def test_failed_crc_even_matching_bytes_is_not_idle_permission(self):
        self.prepare_failed_read()
        result=runner.analyze_retained(self.args.out,self.manifest,self.header,self.reference)
        self.assertTrue(result['comparison']['bytes_equal'])
        self.assertFalse(result['successful_idle_permission'])
        self.assertEqual(result['sd_error'],14)

    def test_failure_stops_after_read_and_retains_full_destination(self):
        def fake(command,**kwargs):
            if 'read' in command:
                self.prepare_failed_read()
                raise subprocess.CalledProcessError(1,command)
            return SimpleNamespace(returncode=0)
        with patch.object(runner,'admission',return_value=self.mocked_admission()), \
                patch.object(runner.subprocess,'run',side_effect=fake) as command:
            result=runner.run(self.args)
        self.assertFalse(result['passed'])
        self.assertEqual(command.call_count,2)
        self.assertTrue(result['retained']['full_buffer_retained'])
        self.assertFalse((self.args.out/'final-idle').exists())
        self.assertFalse((self.args.out/'result.json').exists())

    def test_timeout_does_not_launch_any_extra_hardware_reader(self):
        def fake(command,**kwargs):
            raise subprocess.TimeoutExpired(command,kwargs['timeout'])
        with patch.object(runner,'admission',return_value=self.mocked_admission()), \
                patch.object(runner.subprocess,'run',side_effect=fake) as command:
            result=runner.run(self.args)
        self.assertFalse(result['passed'])
        self.assertEqual(command.call_count,1)
        self.assertFalse(result['retained']['full_buffer_retained'])

    def test_unexpected_camera_or_write_activity_rejected(self):
        self.prepare_failed_read()
        proof=runner.read(self.args.out/'read/proof.json')
        proof['arm']=123
        write(self.args.out/'read/proof.json',proof)
        with self.assertRaisesRegex(ValueError,'Camera activity'):
            runner.analyze_retained(self.args.out,self.manifest,self.header,self.reference)
        proof['arm']=0
        proof['card_write_lo']=1
        write(self.args.out/'read/proof.json',proof)
        with self.assertRaisesRegex(ValueError,'sector writes'):
            runner.analyze_retained(self.args.out,self.manifest,self.header,self.reference)

    def test_wrong_mode_or_camera_reset_level_rejected(self):
        self.prepare_failed_read()
        path=self.args.out/'read/read-diagnostics.json'
        diag=runner.read(path)
        diag['diagnostics']['mode']=1
        write(path,diag)
        with self.assertRaisesRegex(ValueError,'wrong mode'):
            runner.analyze_retained(self.args.out,self.manifest,self.header,self.reference)
        diag['diagnostics']['mode']=0
        diag['camera']['idr']=0x20
        write(path,diag)
        with self.assertRaisesRegex(ValueError,'Camera held-reset'):
            runner.analyze_retained(self.args.out,self.manifest,self.header,self.reference)

    def test_success_requires_second_download_matches_diagnostic_and_reference(self):
        self.prepare_failed_read()
        proof=runner.read(self.args.out/'read/proof.json')
        proof.update(result=0,sd_error=0,cleanup_error=0)
        write(self.args.out/'read/proof.json',proof)
        diag=runner.read(self.args.out/'read/read-diagnostics.json')
        diag['operation_result']=0
        diag['diagnostics']['result']=0
        write(self.args.out/'read/read-diagnostics.json',diag)
        card=dict(**self.identity,clock_hz=25000000,written_sectors=0,read_sectors=1,error=0,
            cleanup_error=0,initialized=0,controller_owned=0,media_idle=1,
            bus_width_proof=dict(configured_clkcr=0x34003,negotiated_width=4))
        verified=dict(passed=True,binary_sha256='test',proof=proof,card=card,
            read_sha256=hashlib.sha256(self.header).hexdigest())
        write(self.args.out/'read/verified.json',verified)
        (self.args.out/'read/sectors.bin').write_bytes(self.header)
        result=runner.analyze_retained(self.args.out,self.manifest,self.header,self.reference)
        self.assertTrue(result['successful_idle_permission'])
        (self.args.out/'read/sectors.bin').write_bytes(bytes(512))
        with self.assertRaisesRegex(ValueError,'Successful sector download'):
            runner.analyze_retained(self.args.out,self.manifest,self.header,self.reference)


if __name__=='__main__':
    unittest.main()
